"""Classifier interpretation: fast, local classifiers first, the Qwen interpreter otherwise.

Topic: one classifier per case over its facts plus "no topic". Tone: empathy (0-2) and
confrontation heads shared by all cases. Both are logistic regression on the local
embedding model's vectors plus word and character n-grams, trained at start-up from
data/training/ (design and thresholds: docs/QWEN-SPECIFICATION.md, section 11).

A classifier answer is used only when it is confident; otherwise the matching Qwen call
runs, exactly as without the cascade. The same deterministic tone rules apply to both
routes. The classifiers see the trainee's line only, never fact content.
"""

import asyncio
import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sparse
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_union

from psychiatry_api.cases import Case
from psychiatry_api.config import ROOT
from psychiatry_api.finetune.format import FORMAT_VERSION, SYSTEM, parse, render
from psychiatry_api.models.contracts import EmbeddingModel, EmbeddingRequest
from psychiatry_api.models.errors import ModelError
from psychiatry_api.roleplay.calls import ModelCall
from psychiatry_api.roleplay.disclosure import Interpretation
from psychiatry_api.roleplay.interpret import (
    INTERPRET_PROMPT,
    SPECIFIC_MIN_WORDS,
    TAG_QUESTION,
    TONE_PROMPT,
    ModelInterpreter,
    asks_for_information,
)

log = logging.getLogger(__name__)
TRAINING = ROOT / "data/training"
NO_TOPIC = "none"
# Weight of the embedding block relative to the n-gram block in the combined features.
EMBEDDING_WEIGHT = 2.0
TOPIC_C, TONE_C = 16.0, 4.0
# Chosen on out-of-fold training predictions (98.5% exact for topics; no false empathy or
# confrontation for tone). Tone moved from 0.8 to 0.85 when the impatient lines were added
# (2026-10-13): at 0.8 the retrained heads gave two false empathy ratings.
TOPIC_THRESHOLD = 0.9
TONE_THRESHOLD = 0.85
CLASSIFIER_DESIGN = "classifier-v1"


def classifier_cache(settings) -> Path:
    """Embedding cache for training lines, one file per embedding model revision."""
    return settings.classifier_cache / f"embeddings-{settings.embedding_model_revision[:12]}.npz"


# ------------------------------------------------------------------------------ text rules
def statements(text: str) -> str:
    """The parts that can carry empathy: sentences that are not questions."""
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return " ".join(p for p in parts if p and not p.endswith("?"))


def challenge_text(text: str) -> str:
    """The parts that can be confrontational: sentences that are not plain questions."""
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return " ".join(p for p in parts if p and not asks_for_information(p))


def stacked(text: str) -> bool:
    """Two or more questions in one line: a single-answer classifier cannot handle it."""
    return text.count("?") >= 2


JOINED_QUESTION = re.compile(
    r",?\s+(?:and|or)\s+(?:do|does|did|is|are|was|were|have|has|had|can|could|would|will|"
    r"how|what|when|where|who|why|any|anything)\b",
    re.I,
)


def compound(text: str) -> bool:
    """Two questions in one line, as separate questions or joined ("Do you smoke, and how is
    your appetite?"). The student tends to label only one of them."""
    return stacked(text) or (text.rstrip().endswith("?") and bool(JOINED_QUESTION.search(text)))


def decide(text: str, label: str, confidence: float, threshold: float) -> frozenset[str] | None:
    """The classifier's topics if confident, else None (defer to the Qwen topic call)."""
    if stacked(text) or confidence < threshold:
        return None
    return frozenset() if label == NO_TOPIC else frozenset({label})


# ------------------------------------------------------------------------- training data
@dataclass(frozen=True)
class TopicItem:
    case_id: str
    utterance: str
    topics: frozenset[str]
    # The case version these phrasings were written for (the training file's case_version).
    case_version: str | None = None


@dataclass(frozen=True)
class ToneItem:
    case_id: str
    utterance: str
    empathy: int
    confrontational: bool


def label_of(item: TopicItem) -> str:
    return next(iter(item.topics)) if item.topics else NO_TOPIC


def topic_training(root: Path = TRAINING) -> list[TopicItem]:
    items = []
    for path in sorted((root / "topics").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for item in data["items"]:
            items.append(
                TopicItem(
                    data["case_id"],
                    item["utterance"],
                    frozenset(item["topics"]),
                    data.get("case_version"),
                )
            )
    return items


def tone_training(root: Path = TRAINING) -> list[ToneItem]:
    items = []
    for path in sorted((root / "tone").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for item in data["items"]:
            items.append(
                ToneItem(
                    data["case_id"], item["utterance"], item["empathy"], item["confrontational"]
                )
            )
    return items


def training_digest(root: Path = TRAINING) -> str:
    """Identifies the training data, so session logs record which classifiers ran."""
    digest = hashlib.sha256()
    for path in sorted(root.glob("*/*.yaml")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


# ---------------------------------------------------------------------------- embeddings
class Embedder:
    """Embeds texts with the local embedding model, caching vectors on disk by text."""

    def __init__(self, model: EmbeddingModel, cache: Path | None):
        self.model, self.cache = model, cache
        self.vectors: dict[str, np.ndarray] = {}
        if cache and cache.exists():
            stored = np.load(cache)
            self.vectors = {key: stored[key] for key in stored.files}

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(f"\n{text}".encode()).hexdigest()

    async def embed(self, texts: list[str]) -> np.ndarray:
        missing = list(dict.fromkeys(t for t in texts if self.key(t) not in self.vectors))
        for start in range(0, len(missing), 32):
            batch = missing[start : start + 32]
            result = await self.model.embed(EmbeddingRequest(texts=tuple(batch)))
            for text, vector in zip(batch, result.vectors, strict=True):
                self.vectors[self.key(text)] = np.asarray(vector, dtype=np.float32)
        return np.stack([self.vectors[self.key(t)] for t in texts])

    async def embed_fresh(self, texts: list[str]) -> np.ndarray:
        """Embeds without caching: trainee lines at runtime are not stored."""
        result = await self.model.embed(EmbeddingRequest(texts=tuple(texts)))
        return np.asarray(result.vectors, dtype=np.float32)

    def save(self) -> None:
        if self.cache:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(self.cache, **self.vectors)


# ---------------------------------------------------------------------------- classifier
def ngrams():
    return make_union(
        TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True),
    )


class Classifier:
    """Logistic regression on [word and character n-grams, embedding x EMBEDDING_WEIGHT]."""

    def __init__(self, c: float):
        self.c = c

    def fit(self, texts: list[str], vectors: np.ndarray, labels: list):
        self.vectorizer = ngrams().fit(texts)
        self.model = LogisticRegression(C=self.c, max_iter=5000)
        self.model.fit(self.features(texts, vectors), labels)
        return self

    def features(self, texts, vectors):
        return sparse.hstack(
            [self.vectorizer.transform(texts), sparse.csr_matrix(vectors * EMBEDDING_WEIGHT)]
        ).tocsr()

    def predict(self, texts, vectors) -> list[tuple[object, float]]:
        p = self.model.predict_proba(self.features(texts, vectors))
        return [(self.model.classes_[row.argmax()], float(row.max())) for row in p]


@dataclass
class ToneHeads:
    empathy: Classifier
    confrontation: Classifier


def fit_topic(case: Case, items: list[TopicItem], vectors: np.ndarray, label_vectors) -> Classifier:
    """Single-topic and no-topic lines plus the facts' own labels; two-topic lines are left
    out because one classifier gives one answer."""
    extra = [(label, fact.id) for fact in case.facts for label in fact.asked_about]
    return Classifier(TOPIC_C).fit(
        [i.utterance for i in items] + [text for text, _ in extra],
        np.vstack([vectors, label_vectors]),
        [label_of(i) for i in items] + [fact for _, fact in extra],
    )


def fit_tone(items: list[ToneItem], said_vectors, challenge_vectors) -> ToneHeads:
    with_statements = [i for i in items if statements(i.utterance)]
    with_challenge = [i for i in items if challenge_text(i.utterance)]
    return ToneHeads(
        Classifier(TONE_C).fit(
            [statements(i.utterance) for i in with_statements],
            said_vectors,
            [i.empathy for i in with_statements],
        ),
        Classifier(TONE_C).fit(
            [challenge_text(i.utterance) for i in with_challenge],
            challenge_vectors,
            [i.confrontational for i in with_challenge],
        ),
    )


@dataclass(frozen=True)
class Rating:
    """The classifiers' best answers and confidences for one line."""

    topics: frozenset[str] | None  # None: not confident, or no classifier for this case
    topic_confidence: float | None
    empathy: int
    empathy_confidence: float
    confrontational: bool
    confrontation_confidence: float
    # The topic classifier's best label even when it is not confident (NO_TOPIC or a fact
    # ID); None if the case has no topic classifier.
    leaning: str | None = None

    @property
    def tone_confident(self) -> bool:
        return min(self.empathy_confidence, self.confrontation_confidence) >= TONE_THRESHOLD

    @property
    def tone_confidence(self) -> float:
        return min(self.empathy_confidence, self.confrontation_confidence)


class TrainedClassifiers:
    """Trained once per process, on first use, from data/training/."""

    def __init__(self, model: EmbeddingModel, cache: Path | None = None, root: Path = TRAINING):
        self.embedder = Embedder(model, cache)
        self.root = root
        self.version = f"{CLASSIFIER_DESIGN}-{training_digest(root)}"
        self.topic: dict[str, Classifier] = {}
        self.tone: ToneHeads | None = None
        # Cases whose training phrasings were written for another case version. They get
        # no topic classifier, so their topics go to the model route instead.
        self.stale: dict[str, tuple[str, ...]] = {}
        self.lock = asyncio.Lock()

    async def ready(self, cases: dict[str, Case]) -> None:
        async with self.lock:
            if self.tone is not None:
                return
            by_case = defaultdict(list)
            stale = defaultdict(set)
            for item in topic_training(self.root):
                if item.case_id not in cases:
                    continue
                if item.case_version != cases[item.case_id].version:
                    stale[item.case_id].add(str(item.case_version))
                elif len(item.topics) <= 1:
                    by_case[item.case_id].append(item)
            for case_id, versions in stale.items():
                by_case.pop(case_id, None)
                log.warning(
                    "Topic training for %s was written for version %s, not %s; "
                    "its topics use the model route until the phrasings are updated",
                    case_id,
                    ", ".join(sorted(versions)),
                    cases[case_id].version,
                )
            self.stale = {case_id: tuple(sorted(v)) for case_id, v in stale.items()}
            topic = {}
            for case_id, items in by_case.items():
                case = cases[case_id]
                vectors = await self.embedder.embed([i.utterance for i in items])
                labels = await self.embedder.embed(
                    [lab for f in case.facts for lab in f.asked_about]
                )
                topic[case_id] = await asyncio.to_thread(fit_topic, case, items, vectors, labels)
            tone_items = tone_training(self.root)
            said = await self.embedder.embed(
                [statements(i.utterance) for i in tone_items if statements(i.utterance)]
            )
            challenge = await self.embedder.embed(
                [challenge_text(i.utterance) for i in tone_items if challenge_text(i.utterance)]
            )
            self.embedder.save()
            self.tone = await asyncio.to_thread(fit_tone, tone_items, said, challenge)
            self.topic = topic

    async def rate(self, case: Case, utterance: str) -> Rating:
        said, challenge = statements(utterance), challenge_text(utterance)
        texts = [utterance, said or utterance, challenge or utterance]
        vectors = await self.embedder.embed_fresh(texts)
        topics, topic_confidence, leaning = None, None, None
        if case.id in self.topic:
            [(label, topic_confidence)] = self.topic[case.id].predict([utterance], vectors[:1])
            topics = decide(utterance, str(label), topic_confidence, TOPIC_THRESHOLD)
            leaning = str(label)
        if said:
            [(level, empathy_confidence)] = self.tone.empathy.predict([said], vectors[1:2])
            level = int(level)
            if level == 2 and len(said.split()) < SPECIFIC_MIN_WORDS:
                level = 1
        else:
            level, empathy_confidence = 0, 1.0
        if challenge:
            [(confront, confrontation_confidence)] = self.tone.confrontation.predict(
                [challenge], vectors[2:3]
            )
            confront = bool(confront)
        else:
            confront, confrontation_confidence = False, 1.0
        return Rating(
            topics,
            topic_confidence,
            level,
            empathy_confidence,
            confront,
            confrontation_confidence,
            leaning,
        )


def asks_question(utterance: str) -> bool:
    """Whether any sentence of the line asks for information: a question opening with a
    question word (interpret.asks_for_information), or a short elliptical one such as "And
    a note?". Tag questions ("..., hasn't he?") are leading, not asking."""
    for sentence in re.split(r"(?<=[.?!])\s+", utterance.strip()):
        if asks_for_information(sentence):
            return True
        short = len(re.findall(r"[a-z']+", sentence.casefold())) <= 5
        if sentence.endswith("?") and short and not TAG_QUESTION.search(sentence):
            return True
    return False


class StudentTopics:
    """The fine-tuned student's topic answer for a line the classifiers are unsure of.

    Only its topics are used; tone stays with the classifiers and Qwen until the student's
    tone passes its evaluation (docs/INTERPRETER-FINETUNE-PLAN.md).
    """

    route = "student"

    def __init__(self, model, served: dict, cross_check: str = "off"):
        if served["format_version"] != FORMAT_VERSION:
            raise ValueError("The served student was trained on another prompt format")
        self.model, self.model_id = model, served["model"]
        self.weights = served["weights_sha256"]
        self.version = f"{FORMAT_VERSION}:{self.model_id}"
        self.cross_check = cross_check
        if cross_check != "off":
            self.version += f":cross-check-{cross_check}"

    async def topics(self, case, history, utterance, leaning: str | None = None):
        """(fact IDs, call record), or (None, call record) if it failed, answered badly or
        should be checked by Qwen. leaning: the topic classifier's best guess though not
        confident (a fact ID or NO_TOPIC), or None if the case has no classifier."""
        # The opening statement is history's first entry, with no interviewer line.
        previous = history[-1] if history and history[-1][0] else None
        try:
            reply = await self.model.complete(SYSTEM, render(case, utterance, previous))
        except ModelError as error:
            return None, ModelCall(
                prompt_version=FORMAT_VERSION,
                status=error.code,
                model_id=self.model_id,
                model_revision=self.weights[:12],
            )
        label = parse(case, reply.text)
        # The student is trusted only when its answer fits the line's form. "None of these"
        # for a line that asks for information is where it misses (held-out test: all three
        # misses), and a topic for a statement or a leading tag question ("He's been
        # aggressive, hasn't he?") is where it releases facts wrongly (fidelity scripts):
        # Qwen decides both.
        # A question answered "none" stands when the classifiers lean the same way: two
        # independent judges agree (generic openers such as "What's been happening?").
        question = asks_question(utterance)
        unsure = label is not None and (
            (bool(label.asked) and not question)
            or (not label.asked and question and leaning != NO_TOPIC)
        )
        disagrees = (
            label is not None
            and not unsure
            and disagreement(label.asked, leaning, self.cross_check)
        )
        status = "invalid_output" if label is None else "unsure" if unsure else "completed"
        call = ModelCall(
            prompt_version=FORMAT_VERSION,
            status="cross_checked" if disagrees else status,
            model_id=self.model_id,
            model_revision=self.weights[:12],
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            total_ms=reply.total_ms,
            cached_input_tokens=reply.cached_input_tokens,
        )
        return (label.asked if label and not unsure and not disagrees else None), call


RERANK_PROMPT = "rerank-v1"


def fact_document(fact, description: str) -> str:
    """What the reranker compares a line with: the fact's question labels (as the Qwen
    interpreter sees them) and, with labels_content, the fact itself. The reranker's scores
    stay inside the interpreter; nothing it reads reaches the role-player."""
    text = "; ".join(fact.asked_about)
    return f"{text}. Answer: {fact.content.strip()}" if description == "labels_content" else text


def rerank_inputs(case, history, utterance, description: str) -> tuple[str, str, list[str]]:
    """The instruction, query (the line, with the previous exchange for follow-ups) and one
    document per fact, in case order."""
    previous = history[-1] if history and history[-1][0] else None
    role = case.persona.role
    query = (
        f'Previous: doctor: "{previous[0]}" {role}: "{previous[1]}"\nLine: {utterance}'
        if previous
        else utterance
    )
    instruction = (
        f"Given a line a doctor says to a {role} in a psychiatric interview, judge whether "
        "the line asks about the topic in the Document."
    )
    return instruction, query, [fact_document(f, description) for f in case.facts]


def reranked(scores: dict[str, float], threshold: float, margin: float) -> frozenset[str] | None:
    """The reranker's decision: no topic when nothing reaches the threshold; the top fact when
    it leads the next by at least the margin; None (unsure: Qwen decides) when two facts are
    too close to call."""
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < threshold:
        return frozenset()
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin:
        return None
    return frozenset({ranked[0][0]})


class RerankerTopics:
    """A cross-encoder that scores the line against each of the case's facts
    (docs/RERANKER-PLAN.md); a drop-in alternative to StudentTopics, with the same rules for
    the line's form and the same optional cross-check."""

    route = "reranker"

    def __init__(
        self,
        model,
        served: dict,
        threshold: float,
        margin: float,
        description: str = "labels",
        cross_check: str = "off",
    ):
        self.model, self.model_id, self.weights = model, served["model"], served["weights_sha256"]
        self.threshold, self.margin, self.description = threshold, margin, description
        self.cross_check = cross_check
        self.version = f"{RERANK_PROMPT}:{self.model_id}:{description}:t{threshold}:m{margin}" + (
            f":cross-check-{cross_check}" if cross_check != "off" else ""
        )

    async def topics(self, case, history, utterance, leaning: str | None = None):
        facts = list(case.facts)
        instruction, query, documents = rerank_inputs(case, history, utterance, self.description)
        try:
            reply = await self.model.score(instruction, query, documents)
        except ModelError as error:
            return None, ModelCall(
                prompt_version=RERANK_PROMPT,
                status=error.code,
                model_id=self.model_id,
                model_revision=self.weights[:12],
            )
        asked = reranked(
            {f.id: s for f, s in zip(facts, reply.scores, strict=True)},
            self.threshold,
            self.margin,
        )
        question = asks_question(utterance)
        unsure = asked is None or (
            (bool(asked) and not question) or (not asked and question and leaning != NO_TOPIC)
        )
        disagrees = not unsure and disagreement(asked, leaning, self.cross_check)
        call = ModelCall(
            prompt_version=RERANK_PROMPT,
            status="cross_checked" if disagrees else "unsure" if unsure else "completed",
            model_id=self.model_id,
            model_revision=self.weights[:12],
            total_ms=reply.total_ms,
        )
        return (None if unsure or disagrees else asked), call


def disagreement(asked: frozenset[str], leaning: str | None, mode: str) -> bool:
    """Whether the student's topic should go to Qwen because the classifiers' best guess
    differs (docs/STUDENT-CROSS-CHECK-PLAN.md). Wrong releases were mostly a neighbouring
    fact chosen with confidence; two independent judges disagreeing marks that case."""
    if mode == "off" or not asked or leaning is None or leaning in asked:
        return False
    return mode == "all" or leaning != NO_TOPIC


class CascadeInterpreter:
    """Classifiers first; the Qwen topic or tone call when they are not confident."""

    id = "cascade-v1"

    def __init__(
        self,
        classifiers: TrainedClassifiers,
        model: ModelInterpreter,
        cases: dict[str, Case],
        student: "StudentTopics | None" = None,
    ):
        # Every case is needed up front: the classifiers are trained once, on first use.
        self.classifiers, self.model, self.cases, self.student = classifiers, model, cases, student
        self.prompt_version = f"{classifiers.version}+{INTERPRET_PROMPT}+{TONE_PROMPT}"
        if student:
            self.id = "cascade-v2"
            self.prompt_version += f"+{student.version}"
        # The rating (and student answer) behind the last forecast, reused when the same
        # utterance is interpreted.
        self._rated: tuple[str, str, object] | None = None
        self._studied: tuple[tuple, tuple] | None = None

    async def _rate(self, case, utterance):
        if self._rated and self._rated[:2] == (case.id, utterance):
            return self._rated[2]
        await self.classifiers.ready(self.cases | {case.id: case})
        rating = await self.classifiers.rate(case, utterance)
        self._rated = (case.id, utterance, rating)
        return rating

    async def _ask_student(self, case, history, utterance, rating):
        key = (case.id, utterance, tuple(history[-1]) if history else None)
        if self._studied and self._studied[0] == key:
            return self._studied[1]
        answer = await self.student.topics(case, history, utterance, leaning=rating.leaning)
        self._studied = (key, answer)
        return answer

    async def forecast(self, case, utterance, question=None, history=None):
        try:
            rating = await self._rate(case, utterance)
        except ModelError:
            return True
        topics_slow = False
        if rating.topics is None:
            # With a student, the turn is slow only if it hands the line on to Qwen.
            if self.student is None or compound(utterance):
                topics_slow = True
            else:
                asked, _ = await self._ask_student(case, history or [], utterance, rating)
                topics_slow = asked is None
        return topics_slow or not rating.tone_confident or question is not None

    async def interpret(self, case, state, history, utterance, question=None):
        try:
            rating = await self._rate(case, utterance)
            self._rated = None
        except ModelError:
            # Embedding server unavailable: behave exactly like the Qwen interpreter.
            interpretation, calls, flags = await self.model.interpret(
                case, state, history, utterance, question
            )
            return interpretation, calls, [*flags, "classifier_unavailable"]
        calls, flags = [], []
        student = None
        # Two questions in one line go to Qwen: the student tends to label only one.
        if rating.topics is None and self.student is not None and not compound(utterance):
            student, call = await self._ask_student(case, history, utterance, rating)
            self._studied = None
            calls.append(call)
            if student is None:
                flags.append(
                    {"unsure": "student_unsure", "cross_checked": "student_cross_checked"}.get(
                        call.status, "student_failed"
                    )
                )
        if rating.topics is not None:
            asked, focus, topic_route = rating.topics, None, "classifier"
        elif student is not None:
            asked, focus, topic_route = student, None, self.student.route
        else:
            found, topic_calls, topic_flags = await self.model.topics(case, history, utterance)
            calls += topic_calls
            flags += topic_flags
            asked, focus, topic_route = found.asked, found.focus, "model"
        # Only the Qwen tone call judges whether a pending character question was answered.
        if rating.tone_confident and question is None:
            empathy, confrontational, answered = rating.empathy, rating.confrontational, False
            tone_route = "classifier"
        else:
            tone_route = "model"
            rated, tone_call = await self.model.rated_tone(case, history, utterance, question)
            calls.append(tone_call)
            if rated is None:
                empathy, confrontational, answered = 0, False, False
                flags.append("tone_failed")
            else:
                empathy, confrontational, answered = rated
        interpretation = Interpretation(
            asked=asked,
            empathy=empathy,
            confrontational=confrontational,
            answered=answered,
            focus=focus,
            topic_route=topic_route,
            topic_confidence=rating.topic_confidence,
            topic_leaning=rating.leaning,
            tone_route=tone_route,
            tone_confidence=rating.tone_confidence,
        )
        return interpretation, calls, flags


def student_topics(settings) -> "StudentTopics | RerankerTopics | None":
    """The served topic decider between the classifiers and Qwen: the reranker when
    TOPIC_DECIDER=reranker and npm run reranker:start attests it, else the student when
    STUDENT_BACKEND=local and npm run student:start attests it."""
    from psychiatry_api.models.student import StudentModel, running_student

    if settings.topic_decider == "reranker":
        return reranker_topics(settings)
    if settings.student_backend != "local":
        return None
    served = running_student(settings.student_state_file)
    if served is None:
        return None
    model = StudentModel(settings.student_base_url, served["model"], settings.model_timeout_seconds)
    return StudentTopics(model, served, settings.student_cross_check)


def build_cascade(settings, model: ModelInterpreter, cases: dict[str, Case]) -> CascadeInterpreter:
    """A cascade with freshly trained classifiers (evaluation scripts; the API keeps one
    set of classifiers per process)."""
    from psychiatry_api.models.selection import embedding_model

    classifiers = TrainedClassifiers(embedding_model(settings), classifier_cache(settings))
    return CascadeInterpreter(classifiers, model, cases, student_topics(settings))


def reranker_topics(settings) -> RerankerTopics | None:
    from psychiatry_api.models.reranker import RerankerModel, running_reranker

    served = running_reranker(settings.reranker_state_file)
    if served is None:
        return None
    model = RerankerModel(
        settings.reranker_base_url, served["model"], settings.model_timeout_seconds
    )
    return RerankerTopics(
        model,
        served,
        settings.reranker_threshold,
        settings.reranker_margin,
        settings.reranker_description,
        settings.student_cross_check,
    )
