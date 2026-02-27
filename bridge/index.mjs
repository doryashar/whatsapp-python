#!/usr/bin/env node
/**
 * WhatsApp Bridge - JSON-RPC over stdio
 * Communicates with Python FastAPI via stdin/stdout
 */

import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  isJidGroup,
} from "@whiskeysockets/baileys";
import pino from "pino";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import QRCode from "qrcode";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || path.join(__dirname, "..", "data", "auth");

const logger = pino({ level: "silent" });

let sock = null;
let currentQr = null;
let connectionState = "disconnected";
let selfInfo = null;

function sendResponse(id, result) {
  const msg = JSON.stringify({ jsonrpc: "2.0", result, id });
  process.stdout.write(msg + "\n");
}

function sendError(id, code, message) {
  const msg = JSON.stringify({ jsonrpc: "2.0", error: { code, message }, id });
  process.stdout.write(msg + "\n");
}

function sendEvent(method, params) {
  const msg = JSON.stringify({ jsonrpc: "2.0", method, params });
  process.stdout.write(msg + "\n");
}

async function ensureAuthDir() {
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }
}

function toJid(phone) {
  let jid = phone.replace(/[^\d-]/g, "");
  if (!jid.includes("@")) {
    jid = jid.includes("-") ? `${jid}@g.us` : `${jid}@s.whatsapp.net`;
  }
  return jid;
}

function extractMessageContent(message) {
  const msg = message.message;
  if (!msg) return { text: "", type: "empty" };

  if (msg.conversation) return { text: msg.conversation, type: "text" };
  if (msg.extendedTextMessage?.text) {
    return {
      text: msg.extendedTextMessage.text,
      type: "text",
      contextInfo: msg.extendedTextMessage.contextInfo,
    };
  }
  if (msg.imageMessage) {
    return {
      text: msg.imageMessage.caption || "",
      type: "image",
      mimetype: msg.imageMessage.mimetype,
    };
  }
  if (msg.videoMessage) {
    return {
      text: msg.videoMessage.caption || "",
      type: "video",
      mimetype: msg.videoMessage.mimetype,
    };
  }
  if (msg.audioMessage) {
    return { text: "", type: "audio", mimetype: msg.audioMessage.mimetype };
  }
  if (msg.documentMessage) {
    return {
      text: "",
      type: "document",
      filename: msg.documentMessage.fileName,
      mimetype: msg.documentMessage.mimetype,
    };
  }
  if (msg.stickerMessage) return { text: "", type: "sticker" };
  if (msg.locationMessage) {
    return {
      text: `https://maps.google.com/?q=${msg.locationMessage.degreesLatitude},${msg.locationMessage.degreesLongitude}`,
      type: "location",
      latitude: msg.locationMessage.degreesLatitude,
      longitude: msg.locationMessage.degreesLongitude,
    };
  }
  if (msg.contactMessage) {
    return { text: msg.contactMessage.displayName || "Unknown", type: "contact" };
  }

  return { text: "", type: "unknown" };
}

async function createSocket() {
  await ensureAuthDir();

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    version,
    logger,
    printQRInTerminal: false,
    browser: ["whatsapp-python-api", "bridge", "1.0.0"],
    syncFullHistory: false,
    markOnlineOnConnect: true,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQr = qr;
      connectionState = "pending_qr";

      try {
        const qrDataUrl = await QRCode.toDataURL(qr);
        sendEvent("qr", { qr, qr_data_url: qrDataUrl });
      } catch (err) {
        sendEvent("qr", { qr, qr_data_url: null });
      }
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      connectionState = "disconnected";
      selfInfo = null;

      sendEvent("disconnected", {
        reason: statusCode,
        should_reconnect: statusCode !== DisconnectReason.loggedOut,
      });

      if (statusCode === DisconnectReason.loggedOut) {
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
      }
    }

    if (connection === "open") {
      connectionState = "connected";
      currentQr = null;

      const user = sock.user;
      selfInfo = {
        jid: user?.id,
        phone: user?.id?.split(":")[0].split("@")[0],
        name: user?.name,
      };

      sendEvent("connected", selfInfo);
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (msg.key.fromMe) continue;

      const remoteJid = msg.key.remoteJid;
      if (remoteJid.endsWith("@status") || remoteJid.endsWith("@broadcast")) {
        continue;
      }

      const isGroup = isJidGroup(remoteJid);
      const content = extractMessageContent(msg);

      const eventData = {
        id: msg.key.id,
        from: isGroup ? msg.key.participant : remoteJid,
        chat_jid: remoteJid,
        is_group: isGroup,
        push_name: msg.pushName || null,
        text: content.text,
        type: content.type,
        timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now(),
      };

      sendEvent("message", eventData);

      try {
        await sock.readMessages([{ remoteJid, id: msg.key.id, fromMe: false }]);
      } catch {}
    }
  });

  return sock;
}

const methods = {
  async login() {
    if (connectionState === "connected") {
      return { status: "already_connected", ...selfInfo };
    }

    if (!sock) {
      await createSocket();
    }

    if (currentQr) {
      const qrDataUrl = await QRCode.toDataURL(currentQr);
      return { status: "qr_ready", qr: currentQr, qr_data_url: qrDataUrl };
    }

    return { status: "pending", connection_state: connectionState };
  },

  async logout() {
    if (sock) {
      try {
        sock.ws?.close();
      } catch {}
      sock = null;
    }

    if (fs.existsSync(AUTH_DIR)) {
      fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    }

    connectionState = "disconnected";
    selfInfo = null;
    currentQr = null;

    return { status: "logged_out" };
  },

  async send_message(params) {
    const { to, text, media_url } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);
    let result;

    if (media_url) {
      const buffer = fs.readFileSync(media_url);
      const ext = path.extname(media_url).toLowerCase();
      const mimeTypes = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".pdf": "application/pdf",
      };
      const mimetype = mimeTypes[ext] || "application/octet-stream";

      const msgType = mimetype.startsWith("image/")
        ? "image"
        : mimetype.startsWith("video/")
          ? "video"
          : mimetype.startsWith("audio/")
            ? "audio"
            : "document";

      result = await sock.sendMessage(jid, {
        [msgType]: buffer,
        mimetype,
        caption: text,
        fileName: path.basename(media_url),
      });
    } else {
      result = await sock.sendMessage(jid, { text });
    }

    const messageId = result?.key?.id || "unknown";
    sendEvent("sent", { message_id: messageId, to: jid });

    return { message_id: messageId, to: jid };
  },

  async send_reaction(params) {
    const { chat, message_id, emoji } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(chat);

    await sock.sendMessage(jid, {
      react: {
        text: emoji,
        key: { remoteJid: jid, id: message_id, fromMe: false },
      },
    });

    return { status: "reacted", chat: jid, message_id, emoji };
  },

  async get_status() {
    return {
      connection_state: connectionState,
      self: selfInfo,
      has_qr: currentQr !== null,
    };
  },
};

async function handleRequest(line) {
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    return;
  }

  const { jsonrpc, method, params, id } = request;

  if (jsonrpc !== "2.0" || !method) {
    if (id !== undefined) {
      sendError(id, -32600, "Invalid Request");
    }
    return;
  }

  const handler = methods[method];
  if (!handler) {
    if (id !== undefined) {
      sendError(id, -32601, "Method not found");
    }
    return;
  }

  try {
    const result = await handler(params || {});
    if (id !== undefined) {
      sendResponse(id, result);
    }
  } catch (err) {
    if (id !== undefined) {
      sendError(id, -32000, err.message);
    }
  }
}

process.stdin.setEncoding("utf8");

let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  const lines = buffer.split("\n");
  buffer = lines.pop() || "";

  for (const line of lines) {
    if (line.trim()) {
      handleRequest(line.trim());
    }
  }
});

process.stdin.on("end", () => {
  if (sock) {
    sock.ws?.close();
  }
  process.exit(0);
});

process.on("SIGTERM", () => {
  if (sock) {
    sock.ws?.close();
  }
  process.exit(0);
});

process.on("SIGINT", () => {
  if (sock) {
    sock.ws?.close();
  }
  process.exit(0);
});

sendEvent("ready", { pid: process.pid });

if (process.env.AUTO_LOGIN === "true") {
  createSocket().catch((err) => {
    sendEvent("error", { message: err.message });
  });
}
