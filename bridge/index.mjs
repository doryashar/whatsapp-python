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

const logger = pino({ level: process.env.DEBUG === "true" ? "debug" : "silent" });

let sock = null;
let currentQr = null;
let connectionState = "disconnected";
let selfInfo = null;

const DISCONNECT_REASONS = {
  401: "loggedOut",
  403: "banned",
  405: "invalidSession",
  408: "restartRequired",
  409: "accountSuspended",
  410: "replaced",
  411: "replaced",
  412: "replaced",
  413: "timedOut",
  414: "timedOut",
  415: "timedOut",
  417: "timedOut",
  418: "timedOut",
  428: "connectionClosed",
  429: "connectionClosed",
  430: "connectionClosed",
  431: "connectionLost",
  432: "connectionLost",
  434: "connectionReplaced",
  435: "connectionReplaced",
  436: "timedOut",
  440: "serviceUnavailable",
  441: "serviceUnavailable",
  442: "serviceUnavailable",
  500: "unknown",
  501: "unknown",
  502: "unknown",
  503: "unavailable",
  504: "timedOut",
  515: "timedOut",
  516: "timedOut",
  518: "timedOut",
  519: "timedOut",
  520: "timedOut",
};

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

async function exportAuthState() {
  const authData = { creds: null, keys: {} };
  
  const credsPath = path.join(AUTH_DIR, "creds.json");
  if (fs.existsSync(credsPath)) {
    authData.creds = JSON.parse(fs.readFileSync(credsPath, "utf-8"));
  }
  
  const keysDir = path.join(AUTH_DIR, "keys");
  if (fs.existsSync(keysDir)) {
    const keyFiles = fs.readdirSync(keysDir);
    for (const file of keyFiles) {
      const filePath = path.join(keysDir, file);
      if (fs.statSync(filePath).isFile()) {
        authData.keys[file] = fs.readFileSync(filePath, "utf-8");
      }
    }
  }
  
  return authData;
}

async function createSocket() {
  await ensureAuthDir();

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  logger.info({ version, authDir: AUTH_DIR }, "Creating WhatsApp socket");

  sock = makeWASocket({
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    version,
    logger,
    printQRInTerminal: false,
    browser: ["Chrome (Linux)", "Chrome", "120.0.0"],
    syncFullHistory: false,
    markOnlineOnConnect: true,
    connectTimeoutMs: 60_000,
    keepAliveIntervalMs: 25_000,
    retryRequestDelayMs: 250,
    maxMsgRetryCount: 5,
    fireInitQueries: true,
    shouldIgnoreJid: (jid) => {
      const isGroup = isJidGroup(jid);
      const isBroadcast = jid.endsWith("@broadcast");
      const isStatus = jid === "status@broadcast";
      return isBroadcast || isStatus;
    },
  });

  sock.ev.on("creds.update", async () => {
    await saveCreds();
    try {
      const authData = await exportAuthState();
      sendEvent("auth.update", authData);
      logger.debug({ hasCreds: !!authData.creds, keyCount: Object.keys(authData.keys).length }, "Sent auth.update event to Python");
    } catch (err) {
      logger.error({ err: err.message }, "Failed to export auth state");
    }
  });

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr, receivedPendingNotifications, isNewLogin, isOnline } = update;

    logger.debug({ 
      connection, 
      hasQr: !!qr, 
      hasLastDisconnect: !!lastDisconnect,
      receivedPendingNotifications,
      isNewLogin,
      isOnline
    }, "Connection update received");

    if (qr) {
      currentQr = qr;
      connectionState = "pending_qr";
      logger.info({ event: "qr_generated" }, "QR code generated - scan with WhatsApp");

      try {
        const qrDataUrl = await QRCode.toDataURL(qr);
        sendEvent("qr", { qr, qr_data_url: qrDataUrl });
      } catch (err) {
        sendEvent("qr", { qr, qr_data_url: null });
      }
    }

    if (connection === "connecting") {
      connectionState = "connecting";
      logger.info("Connecting to WhatsApp...");
      sendEvent("connecting", {});
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const reasonName = DISCONNECT_REASONS[statusCode] || "unknown";
      const errorMessage = lastDisconnect?.error?.message || "No error message";
      
      connectionState = "disconnected";
      selfInfo = null;
      currentQr = null;

      logger.error({ 
        statusCode, 
        reasonName,
        errorMessage,
        fullError: JSON.stringify(lastDisconnect?.error?.output || {}),
        should_reconnect: statusCode !== DisconnectReason.loggedOut 
      }, "Connection closed");

      sendEvent("disconnected", {
        reason: statusCode,
        reason_name: reasonName,
        error: errorMessage,
        should_reconnect: statusCode !== DisconnectReason.loggedOut,
      });

      // Auto-reconnect for certain errors
      const reconnectableCodes = [408, 409, 428, 429, 430, 431, 432, 436, 504, 515, 516, 518, 519, 520];
      if (reconnectableCodes.includes(statusCode)) {
        const delay = statusCode === 515 ? 5000 : 3000; // Longer delay for timeout
        logger.info({ statusCode, delay }, "Scheduling auto-reconnect");
        
        // Clean up old socket first
        try {
          if (sock) {
            sock.ev.removeAllListeners();
            sock.ws?.close();
            sock = null;
          }
        } catch (cleanupErr) {
          logger.debug({ err: cleanupErr.message }, "Error during socket cleanup");
        }
        
        setTimeout(async () => {
          try {
            logger.info("Attempting auto-reconnect...");
            sendEvent("reconnecting", { reason: statusCode });
            await createSocket();
          } catch (err) {
            logger.error({ err: err.message, stack: err.stack }, "Auto-reconnect failed");
            sendEvent("reconnect_failed", { reason: statusCode, error: err.message });
          }
        }, delay);
      }

      if (statusCode === DisconnectReason.loggedOut) {
        logger.info("Logged out, clearing auth directory");
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

      logger.info({ jid: selfInfo.jid, phone: selfInfo.phone, isNewLogin }, "Connected successfully");
      sendEvent("connected", selfInfo);
    }

    if (receivedPendingNotifications) {
      logger.debug("Received pending notifications - connection stable");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (msg.key.fromMe) continue;

      const remoteJid = msg.key.remoteJid;
      if (remoteJid === "status@broadcast" || remoteJid.endsWith("@broadcast")) {
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
        await sock.logout();
      } catch (e) {
        logger.debug({ err: e.message }, "Logout error (ignored)");
        sock.ws?.close();
      }
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
    const { chat, message_id, emoji, from_me } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(chat);

    await sock.sendMessage(jid, {
      react: {
        text: emoji,
        key: { remoteJid: jid, id: message_id, fromMe: from_me ?? false },
      },
    });

    return { status: "reacted", chat: jid, message_id, emoji };
  },

  async send_poll(params) {
    const { to, poll } = params;
    const { name, values, selectableCount, messageContextInfo } = poll;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    const result = await sock.sendMessage(jid, {
      poll: {
        name,
        values,
        selectableCount: selectableCount ?? 1,
        messageContextInfo,
      },
    });

    const messageId = result?.key?.id || "unknown";
    sendEvent("sent", { message_id: messageId, to: jid, type: "poll" });

    return { message_id: messageId, to: jid };
  },

  async send_typing(params) {
    const { to } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);
    await sock.sendPresenceUpdate("composing", jid);

    return { status: "typing", to: jid };
  },

  async auth_exists() {
    const credsPath = path.join(AUTH_DIR, "creds.json");
    return { exists: fs.existsSync(credsPath) };
  },

  async auth_age() {
    const credsPath = path.join(AUTH_DIR, "creds.json");
    if (!fs.existsSync(credsPath)) {
      return { age_ms: null };
    }
    const stats = fs.statSync(credsPath);
    return { age_ms: Date.now() - stats.mtimeMs };
  },

  async self_id() {
    return {
      jid: selfInfo?.jid || null,
      e164: selfInfo?.phone || null,
      name: selfInfo?.name || null,
    };
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
