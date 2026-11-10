// Preloaded into HeadTTS by tts:start: its server listens on every interface by default;
// this binds any port-only listen() to loopback instead.
import net from "node:net";

const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (port, ...rest) {
  if (typeof port === "number") return listen.call(this, port, "127.0.0.1", ...rest.filter((a) => typeof a === "function"));
  return listen.call(this, port, ...rest);
};
