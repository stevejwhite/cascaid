"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Behaviour, EXPRESSION_SHAPES, type AvatarState, type Mood } from "../lib/avatar/behaviour";
import { cuesForWord, type Cue, VISEMES, weightsAt } from "../lib/avatar/lipsync";
import { onSpeech, wordAt } from "../lib/avatar/speech";

/**
 * A head-and-shoulders 3D character (an open-licence Rocketbox model converted by
 * npm run avatars:install), driven directly: blendshapes for the mouth, blinks and
 * expression; small rotations about each joint's rest pose for head, eyes and breathing.
 */

const BONES = {
  head: "Bip01_Head", neck: "Bip01_Neck", chest: "Bip01_Spine2",
  leftEye: "Bip01_LEye", rightEye: "Bip01_REye",
  leftArm: "Bip01_L_UpperArm", rightArm: "Bip01_R_UpperArm",
};
// Rocketbox characters stand in an A-pose; bring the arms down towards the sides.
const ARMS_DOWN = 38 * (Math.PI / 180);
// Every blendshape this view drives, reset each frame so nothing sticks.
const DRIVEN = [...new Set([...VISEMES.map((v) => `viseme_${v}`), "eyeBlinkLeft", "eyeBlinkRight", ...EXPRESSION_SHAPES])];

interface Joint { bone: THREE.Bone; rest: THREE.Quaternion; restWorld: THREE.Quaternion }

function joint(root: THREE.Object3D, name: string): Joint | null {
  const bone = root.getObjectByName(name) as THREE.Bone | undefined;
  if (!bone) return null;
  return { bone, rest: bone.quaternion.clone(), restWorld: bone.getWorldQuaternion(new THREE.Quaternion()) };
}

/** Rotate a joint by a world-space rotation, relative to its rest pose. */
function turn(j: Joint | null, world: THREE.Quaternion) {
  if (!j) return;
  const local = j.restWorld.clone().invert().multiply(world).multiply(j.restWorld);
  j.bone.quaternion.copy(j.rest).multiply(local);
}

const euler = new THREE.Euler();
const fromAngles = (pitch: number, yaw: number, roll: number) =>
  new THREE.Quaternion().setFromEuler(euler.set(-pitch, yaw, roll, "YXZ"));

export interface AvatarViewProps {
  avatarId: string;
  state: AvatarState;
  mood?: Mood;
  /** Accessible description of who is shown. */
  label: string;
}

export default function AvatarView({ avatarId, state, mood = "neutral", label }: AvatarViewProps) {
  const host = useRef<HTMLDivElement | null>(null);
  const behaviour = useRef<Behaviour | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing">("loading");
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { behaviour.current?.setMood(mood); }, [mood]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const brain = new Behaviour(Math.random, reduced);
    behaviour.current = brain;
    brain.setMood(mood);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xfff4e8, 0x30343a, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 2.4); key.position.set(0.5, 2.0, 2.6); scene.add(key);
    const fill = new THREE.DirectionalLight(0xcfe2ff, 0.7); fill.position.set(-1.2, 1.4, 1); scene.add(fill);
    const camera = new THREE.PerspectiveCamera(24, 1, 0.05, 20);

    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height, false);
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();

    let disposed = false, frame = 0;
    let joints: Record<keyof typeof BONES, Joint | null> | null = null;
    let morphMeshes: THREE.Mesh[] = [];
    let cues: Cue[] = [];
    const clock = new THREE.Clock();
    const stopSpeech = onSpeech((event) => {
      const now = clock.getElapsedTime();
      if (event.type === "start") { cues = []; brain.setState("speaking", now); }
      else if (event.type === "word") {
        const word = wordAt(event.text, event.charIndex, event.charLength);
        cues = [...cues.filter((c) => c.end > now - 1), ...cuesForWord(word, now)];
      } else if (event.type === "cues") {
        brain.setState("speaking", now);
        cues = [...cues.filter((c) => c.end > now - 1),
          ...event.cues.map((c) => ({ ...c, start: c.start + now, end: c.end + now }))];
      } else { cues = []; brain.setState(stateRef.current, now); }
    });

    new GLTFLoader().load(`/avatars/${avatarId}.glb`, (gltf) => {
      if (disposed) return;
      const model = gltf.scene;
      scene.add(model);
      model.updateMatrixWorld(true);
      joints = Object.fromEntries(Object.entries(BONES).map(([k, n]) => [k, joint(model, n)])) as typeof joints;
      model.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.frustumCulled = false;
        if (mesh.morphTargetDictionary) morphMeshes.push(mesh);
      });
      // Frame head and shoulders from eye level (the head joint sits at the base of the skull).
      const eye = joints!.leftEye?.bone.getWorldPosition(new THREE.Vector3()) ?? new THREE.Vector3(0, 1.62, 0);
      const centre = eye.y - 0.1;
      camera.position.set(0, centre + 0.02, eye.z + 1.3);
      camera.lookAt(0, centre, eye.z);
      key.target.position.set(0, eye.y, eye.z); scene.add(key.target);
      setStatus("ready");
    }, undefined, () => { if (!disposed) setStatus("missing"); });

    const animate = () => {
      frame = requestAnimationFrame(animate);
      const now = clock.getElapsedTime();
      if (stateRef.current !== brain.getState() && brain.getState() !== "speaking") brain.setState(stateRef.current, now);
      brain.setMouth(weightsAt(cues, now));
      const f = brain.update(now);
      if (joints) {
        turn(joints.neck, fromAngles(f.head.pitch * 0.4, f.head.yaw * 0.4, f.head.roll * 0.4));
        turn(joints.head, fromAngles(f.head.pitch * 0.6, f.head.yaw * 0.6, f.head.roll * 0.6));
        turn(joints.chest, fromAngles(0.012 * (f.breath - 0.5), 0, 0));
        const eyes = fromAngles(f.eyes.pitch, f.eyes.yaw, 0);
        turn(joints.leftEye, eyes); turn(joints.rightEye, eyes);
        turn(joints.leftArm, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -ARMS_DOWN));
        turn(joints.rightArm, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), ARMS_DOWN));
      }
      for (const mesh of morphMeshes) {
        const dict = mesh.morphTargetDictionary!, influences = mesh.morphTargetInfluences!;
        for (const name of DRIVEN) { const i = dict[name]; if (i !== undefined) influences[i] = f.morphs[name] ?? 0; }
      }
      renderer.render(scene, camera);
      element.dataset.frames = String(Number(element.dataset.frames ?? 0) + 1);
    };
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      stopSpeech();
      observer.disconnect();
      renderer.dispose();
      renderer.domElement.remove();
      morphMeshes = [];
    };
    // The model and renderer are rebuilt only when the character changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatarId]);

  return <div className="avatar" ref={host} role="img" aria-label={label} data-status={status} data-mood={mood}>
    {status === "missing" && <p className="avatar-missing">Character not installed. Run <code>npm run avatars:install</code>.</p>}
  </div>;
}
