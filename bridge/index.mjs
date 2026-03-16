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
  generateWAMessageFromContent,
} from "@whiskeysockets/baileys";
import pino from "pino";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import QRCode from "qrcode";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || path.join(__dirname, "..", "data", "auth");

const AUTO_MARK_READ = process.env.AUTO_MARK_READ !== "false";
const logger = pino({ level: process.env.DEBUG === "true" ? "debug" : "silent" });

let sock = null;
let currentQr = null;
let connectionState = "disconnected";
let selfInfo = null;
let instanceSettings = {
  reject_call: false,
  msg_call: "",
  groups_ignore: false,
  always_online: false,
  read_messages: false,
  read_status: false,
  sync_full_history: false,
};

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
      url: msg.imageMessage.url,
      mediaKey: msg.imageMessage.mediaKey,
      fileEncSha256: msg.imageMessage.fileEncSha256,
      fileSha256: msg.imageMessage.fileSha256,
      contextInfo: msg.imageMessage.contextInfo,
    };
  }
  if (msg.videoMessage) {
    return {
      text: msg.videoMessage.caption || "",
      type: "video",
      mimetype: msg.videoMessage.mimetype,
      url: msg.videoMessage.url,
      mediaKey: msg.videoMessage.mediaKey,
      fileEncSha256: msg.videoMessage.fileEncSha256,
      fileSha256: msg.videoMessage.fileSha256,
      contextInfo: msg.videoMessage.contextInfo,
    };
  }
  if (msg.audioMessage) {
    return { 
      text: "", 
      type: "audio", 
      mimetype: msg.audioMessage.mimetype,
      url: msg.audioMessage.url,
      mediaKey: msg.audioMessage.mediaKey,
      fileEncSha256: msg.audioMessage.fileEncSha256,
      fileSha256: msg.audioMessage.fileSha256,
      contextInfo: msg.audioMessage.contextInfo,
    };
  }
  if (msg.documentMessage) {
    return {
      text: msg.documentMessage.caption || "",
      type: "document",
      filename: msg.documentMessage.fileName,
      mimetype: msg.documentMessage.mimetype,
      url: msg.documentMessage.url,
      mediaKey: msg.documentMessage.mediaKey,
      fileEncSha256: msg.documentMessage.fileEncSha256,
      fileSha256: msg.documentMessage.fileSha256,
      contextInfo: msg.documentMessage.contextInfo,
    };
  }
  if (msg.stickerMessage) {
    return { 
      text: "", 
      type: "sticker",
      mimetype: msg.stickerMessage.mimetype,
      url: msg.stickerMessage.url,
      mediaKey: msg.stickerMessage.mediaKey,
    };
  }
  if (msg.locationMessage) {
    return {
      text: `https://maps.google.com/?q=${msg.locationMessage.degreesLatitude},${msg.locationMessage.degreesLongitude}`,
      type: "location",
      latitude: msg.locationMessage.degreesLatitude,
      longitude: msg.locationMessage.degreesLongitude,
      name: msg.locationMessage.name || null,
      address: msg.locationMessage.address || null,
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
      const reconnectableCodes = [408, 409, 428, 429, 430, 431, 432, 436, 440, 500, 504, 515, 516, 518, 519, 520];
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

      // Fetch contacts after successful connection
      setTimeout(async () => {
        try {
          const contacts = [];
          
          // Get all contacts from the store
          if (sock.store && sock.store.contacts) {
            for (const [jid, contact] of sock.store.contacts) {
              if (jid && !jid.endsWith('@broadcast') && jid !== 'status@broadcast') {
                const isGroup = isJidGroup(jid);
                contacts.push({
                  jid: jid,
                  name: contact.name || contact.notify || null,
                  phone: isGroup ? null : jid.split('@')[0].split(':')[0],
                  is_group: isGroup,
                });
              }
            }
          }

          logger.info({ contactCount: contacts.length }, "Fetched contacts on connection");
          sendEvent("contacts", { contacts });

          setTimeout(async () => {
            try {
              const chats = [];
              let totalMessages = 0;

              if (sock.store && sock.store.chats) {
                for (const [jid, chat] of sock.store.chats) {
                  if (jid.endsWith('@broadcast') || jid === 'status@broadcast') {
                    continue;
                  }

                  const isGroup = isJidGroup(jid);
                  const chatData = {
                    jid: jid,
                    name: chat.name || chat.subject || null,
                    is_group: isGroup,
                    unread_count: chat.unreadCount || 0,
                    timestamp: chat.conversationTimestamp || 0,
                    messages: [],
                  };

                  if (sock.store.messages) {
                    const chatMessages = sock.store.messages.get(jid);
                    if (chatMessages && chatMessages.length > 0) {
                      const messagesToFetch = chatMessages.slice(-50);
                      
                      for (const msg of messagesToFetch) {
                        if (!msg || !msg.key) continue;

                        const content = extractMessageContent(msg);
                        const messageData = {
                          id: msg.key.id,
                          from_me: msg.key.fromMe || false,
                          from: msg.key.fromMe ? selfInfo?.jid : (isGroup ? msg.key.participant : jid),
                          chat_jid: jid,
                          is_group: isGroup,
                          push_name: msg.pushName || null,
                          text: content.text || "",
                          type: content.type || "text",
                          timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now(),
                        };

                        chatData.messages.push(messageData);
                        totalMessages++;
                      }
                    }
                  }

                  chats.push(chatData);
                }
              }

              logger.info({ chatCount: chats.length, messageCount: totalMessages }, "Fetched chats history on connection");
              sendEvent("chats_history", { chats, total_messages: totalMessages });
            } catch (err) {
              logger.error({ err: err.message }, "Failed to fetch chats history on connection");
            }
          }, 3000);
        } catch (err) {
          logger.error({ err: err.message }, "Failed to fetch contacts on connection");
        }
      }, 2000);
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
        mimetype: content.mimetype || null,
        media_url: content.url || null,
        filename: content.filename || null,
        latitude: content.latitude || null,
        longitude: content.longitude || null,
        location_name: content.name || null,
        location_address: content.address || null,
        media_key: content.mediaKey || null,
        file_enc_sha256: content.fileEncSha256 || null,
        file_sha256: content.fileSha256 || null,
      };

      if (content.contextInfo) {
        eventData.quoted_message_id = content.contextInfo.stanzaId || null;
        eventData.quoted_participant = content.contextInfo.participant || null
        if (content.contextInfo.quotedMessage) {
          eventData.quoted_text = content.contextInfo.quotedMessage.conversation || ""
        }
      }

      sendEvent("message", eventData);

      if (AUTO_MARK_READ) {
        try {
          await sock.readMessages([{ remoteJid, id: msg.key.id, fromMe: false }]);
        } catch (err) {
          logger.debug({ err: err.message, remoteJid, messageId: msg.key.id }, "Failed to mark message as read");
        }
      }
    }
  });

// Message delete event
sock.ev.on("messages.delete", async ({ key }) => {
  if (!key) return;

  logger.info({ messageId: key.id, remoteJid: key.remoteJid }, "Message deleted");

  sendEvent("message_deleted", {
    id: key.id,
    message_id: key.id,
    chat_jid: key.remoteJid,
    remote_jid: key.remoteJid,
    timestamp: Date.now(),
  });
});

// Message read event
sock.ev.on("messages.read", async ({ key }) => {
  if (!key) return;

  logger.debug({ messageId: key.id, remoteJid: key.remoteJid }, "Messages marked as read");

  sendEvent("message_read", {
    id: key.id,
    message_ids: [key.id],
    chat_jid: key.remoteJid,
    remote_jid: key.remoteJid,
    timestamp: Date.now(),
  });
});
}

const methods = {
  async login() {
    if (connectionState === "connected") {
      return { status: "already_connected", ...selfInfo };
    }

    if (sock) {
      try {
        sock.ev.removeAllListeners();
        sock.ws?.close();
      } catch {}
      sock = null;
      currentQr = null;
    }

    await createSocket();

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
    const { to, text, media_url, quoted } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);
    let result;
    let msgType = "text";

    const contextInfo = quoted ? {
      stanzaId: quoted.message_id,
      participant: quoted.chat || quoted.participant,
      quotedMessage: { conversation: quoted.text || "" }
    } : undefined;

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

      msgType = mimetype.startsWith("image/")
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
        ...(contextInfo ? { contextInfo } : {}),
      });
    } else {
      result = await sock.sendMessage(jid, {
        text,
        ...(contextInfo ? { contextInfo } : {}),
      });
    }

    const messageId = result?.key?.id || "unknown";
    const timestamp = typeof result?.messageTimestamp === 'object' 
      ? result.messageTimestamp.low 
      : (result?.messageTimestamp || Date.now());
    sendEvent("sent", { 
      message_id: messageId, 
      to: jid, 
      text: text || "",
      type: msgType,
      timestamp: timestamp
    });

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
    const timestamp = result?.messageTimestamp || Date.now();
    sendEvent("sent", { message_id: messageId, to: jid, type: "poll", timestamp: timestamp });

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

  async get_contacts() {
    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const contacts = [];
      
      // Get all contacts from the store
      if (sock.store && sock.store.contacts) {
        for (const [jid, contact] of sock.store.contacts) {
          if (jid && !jid.endsWith('@broadcast') && jid !== 'status@broadcast') {
            const isGroup = isJidGroup(jid);
            contacts.push({
              jid: jid,
              name: contact.name || contact.notify || null,
              phone: isGroup ? null : jid.split('@')[0].split(':')[0],
              is_group: isGroup,
            });
          }
        }
      }

      logger.info({ contactCount: contacts.length }, "Fetched contacts from WhatsApp");
      return { contacts };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to fetch contacts");
      throw err;
    }
  },

  async get_chats_with_messages(params) {
    const { limit = 50 } = params || {};

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const chats = [];
      let totalMessages = 0;

      if (sock.store && sock.store.chats) {
        for (const [jid, chat] of sock.store.chats) {
          if (jid.endsWith('@broadcast') || jid === 'status@broadcast') {
            continue;
          }

          const isGroup = isJidGroup(jid);
          const chatData = {
            jid: jid,
            name: chat.name || chat.subject || null,
            is_group: isGroup,
            unread_count: chat.unreadCount || 0,
            timestamp: chat.conversationTimestamp || 0,
            messages: [],
          };

          if (sock.store.messages) {
            const chatMessages = sock.store.messages.get(jid);
            if (chatMessages && chatMessages.length > 0) {
              const messagesToFetch = chatMessages.slice(-limit);
              
              for (const msg of messagesToFetch) {
                if (!msg || !msg.key) continue;

                const content = extractMessageContent(msg);
                const messageData = {
                  id: msg.key.id,
                  from_me: msg.key.fromMe || false,
                  from: msg.key.fromMe ? selfInfo?.jid : (isGroup ? msg.key.participant : jid),
                  chat_jid: jid,
                  is_group: isGroup,
                  push_name: msg.pushName || null,
                  text: content.text || "",
                  type: content.type || "text",
                  timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now(),
                };

                chatData.messages.push(messageData);
                totalMessages++;
              }
            }
          }

          chats.push(chatData);
        }
      }

      logger.info({ chatCount: chats.length, messageCount: totalMessages }, "Fetched chats with messages");
      return { chats, total_messages: totalMessages };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to fetch chats with messages");
      throw err;
    }
  },

  async get_profile_picture(params) {
    const { jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const url = await sock.profilePictureUrl(jid, "image");
      return { url };
    } catch (err) {
      logger.debug({ err: err.message, jid }, "Failed to get profile picture");
      return { url: null };
    }
  },

  async delete_message(params) {
    const { to, message_id, from_me } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      await sock.sendMessage(jid, {
        delete: {
          remoteJid: jid,
          id: message_id,
          fromMe: from_me ?? false,
        },
      });

      logger.info({ jid, message_id, from_me: from_me ?? false }, "Message deleted");
      return { status: "deleted", jid, message_id };
    } catch (err) {
      logger.error({ err: err.message, jid, message_id }, "Failed to delete message");
      throw err;
    }
  },

  async mark_read(params) {
    const { to, message_ids } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const keys = message_ids.map((id) => ({
        remoteJid: jid,
        id,
        fromMe: false,
      }));

      await sock.readMessages(keys);

      logger.info({ jid, count: keys.length }, "Messages marked as read");
      return { status: "read", jid, count: keys.length };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to mark messages as read");
      throw err;
    }
  },

  // Group Management Methods
  
  async group_create(params) {
    const { subject, participants, description } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const participantJids = participants.map(p => toJid(p));
      const result = await sock.groupCreate(subject, participantJids);
      
      if (description) {
        await sock.groupUpdateDescription(result.id, description);
      }
      
      logger.info({ groupJid: result.id, subject, participantCount: participants.length }, "Group created");
      return { 
        status: "created", 
        group_jid: result.id, 
        subject,
        participants: participantJids 
      };
    } catch (err) {
      logger.error({ err: err.message, subject }, "Failed to create group");
      throw err;
    }
  },

  async group_update_subject(params) {
    const { group_jid, subject } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      await sock.groupUpdateSubject(jid, subject);
      logger.info({ groupJid: jid, subject }, "Group subject updated");
      return { status: "updated", group_jid: jid, subject };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to update group subject");
      throw err;
    }
  },

  async group_update_description(params) {
    const { group_jid, description } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      await sock.groupUpdateDescription(jid, description);
      logger.info({ groupJid: jid }, "Group description updated");
      return { status: "updated", group_jid: jid };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to update group description");
      throw err;
    }
  },

  async group_update_picture(params) {
    const { group_jid, image_url } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const buffer = fs.readFileSync(image_url);
      await sock.updateProfilePicture(jid, buffer);
      logger.info({ groupJid: jid }, "Group picture updated");
      return { status: "updated", group_jid: jid };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to update group picture");
      throw err;
    }
  },

  async group_get_info(params) {
    const { group_jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const metadata = await sock.groupMetadata(jid);
      return {
        group_jid: jid,
        subject: metadata.subject,
        subject_owner: metadata.subjectOwner,
        subject_time: metadata.subjectTime,
        creation: metadata.creation,
        owner: metadata.owner,
        desc: metadata.desc,
        desc_id: metadata.descId,
        restrict: metadata.restrict,
        announce: metadata.announce,
        size: metadata.size,
        participants: metadata.participants.map(p => ({
          jid: p.id,
          admin: p.admin || null,
        })),
      };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to get group info");
      throw err;
    }
  },

  async group_get_all(params) {
    const { get_participants } = params || {};

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const groups = [];
      
      if (sock.store && sock.store.chats) {
        for (const [jid, chat] of sock.store.chats) {
          if (isJidGroup(jid)) {
            const groupInfo = {
              jid: jid,
              name: chat.name || chat.subject || null,
            };
            
            if (get_participants) {
              try {
                const metadata = await sock.groupMetadata(jid);
                groupInfo.participants = metadata.participants.map(p => ({
                  jid: p.id,
                  admin: p.admin || null,
                }));
                groupInfo.size = metadata.size;
              } catch (err) {
                logger.debug({ err: err.message, jid }, "Could not fetch group metadata");
              }
            }
            
            groups.push(groupInfo);
          }
        }
      }

      logger.info({ groupCount: groups.length }, "Fetched all groups");
      return { groups };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to fetch groups");
      throw err;
    }
  },

  async group_get_participants(params) {
    const { group_jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const metadata = await sock.groupMetadata(jid);
      const participants = metadata.participants.map(p => ({
        jid: p.id,
        admin: p.admin || null,
      }));
      
      logger.info({ groupJid: jid, count: participants.length }, "Fetched group participants");
      return { group_jid: jid, participants };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to get group participants");
      throw err;
    }
  },

  async group_get_invite_code(params) {
    const { group_jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const code = await sock.groupInviteCode(jid);
      logger.info({ groupJid: jid }, "Fetched group invite code");
      return { group_jid: jid, invite_code: code };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to get invite code");
      throw err;
    }
  },

  async group_revoke_invite(params) {
    const { group_jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const newCode = await sock.groupRevokeInvite(jid);
      logger.info({ groupJid: jid }, "Revoked group invite code");
      return { group_jid: jid, new_invite_code: newCode };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to revoke invite code");
      throw err;
    }
  },

  async group_accept_invite(params) {
    const { invite_code } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const groupJid = await sock.groupAcceptInvite(invite_code);
      logger.info({ groupJid, inviteCode: invite_code }, "Accepted group invite");
      return { status: "joined", group_jid: groupJid };
    } catch (err) {
      logger.error({ err: err.message, inviteCode: invite_code }, "Failed to accept group invite");
      throw err;
    }
  },

  async group_get_invite_info(params) {
    const { invite_code } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const info = await sock.groupGetInviteInfo(invite_code);
      return {
        group_jid: info.id,
        subject: info.subject,
        creation: info.creation,
        owner: info.owner,
        desc: info.desc,
        size: info.size,
      };
    } catch (err) {
      logger.error({ err: err.message, inviteCode: invite_code }, "Failed to get invite info");
      throw err;
    }
  },

  async group_update_participant(params) {
    const { group_jid, action, participants } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);
    const participantJids = participants.map(p => toJid(p));

    try {
      const result = await sock.groupParticipantsUpdate(jid, participantJids, action);
      logger.info({ groupJid: jid, action, count: participants.length }, "Updated group participants");
      return { 
        status: "updated", 
        group_jid: jid, 
        action,
        results: result 
      };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid, action }, "Failed to update participants");
      throw err;
    }
  },

  async group_update_setting(params) {
    const { group_jid, action } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      const setting = action === 'announcement' ? 'announcement' : 
                      action === 'not_announcement' ? 'not_announcement' :
                      action === 'locked' ? 'locked' : 'unlocked';
      
      await sock.groupSettingUpdate(jid, setting);
      logger.info({ groupJid: jid, setting }, "Updated group setting");
      return { status: "updated", group_jid: jid, setting };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to update group setting");
      throw err;
    }
  },

  async group_toggle_ephemeral(params) {
    const { group_jid, expiration } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      await sock.groupToggleEphemeral(jid, expiration);
      logger.info({ groupJid: jid, expiration }, "Toggled group ephemeral");
      return { status: "updated", group_jid: jid, expiration };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to toggle ephemeral");
      throw err;
    }
  },

  async group_leave(params) {
    const { group_jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(group_jid);

    try {
      await sock.groupLeave(jid);
      logger.info({ groupJid: jid }, "Left group");
      return { status: "left", group_jid: jid };
    } catch (err) {
      logger.error({ err: err.message, groupJid: jid }, "Failed to leave group");
      throw err;
    }
  },

  // Advanced Messaging

  async send_location(params) {
    const { to, latitude, longitude, name, address } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const result = await sock.sendMessage(jid, {
        location: {
          degreesLatitude: latitude,
          degreesLongitude: longitude,
          name: name || undefined,
          address: address || undefined,
        },
      });

      const messageId = result?.key?.id || "unknown";
      const timestamp = typeof result?.messageTimestamp === 'object' 
        ? result.messageTimestamp.low 
        : (result?.messageTimestamp || Date.now());

      logger.info({ jid, messageId }, "Location sent");
      sendEvent("sent", { message_id: messageId, to: jid, type: "location", timestamp });
      
      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to send location");
      throw err;
    }
  },

  async send_contact(params) {
    const { to, contacts } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const vcard = (contact) => {
        const vcard = 'BEGIN:VCARD\n'
          + 'VERSION:3.0\n'
          + `FN:${contact.name || contact.phone}\n`
          + `TEL;type=CELL;type=VOICE;waid=${contact.phone.replace(/[^0-9]/g, '')}:${contact.phone}\n`
          + 'END:VCARD';
        return vcard;
      };

      const message = {
        contacts: {
          displayName: contacts.length > 1 ? `${contacts.length} contacts` : contacts[0].name,
          contacts: contacts.map(c => ({ vcard: vcard(c) })),
        },
      };

      const result = await sock.sendMessage(jid, message);

      const messageId = result?.key?.id || "unknown";
      const timestamp = typeof result?.messageTimestamp === 'object' 
        ? result.messageTimestamp.low 
        : (result?.messageTimestamp || Date.now());

      logger.info({ jid, messageId, count: contacts.length }, "Contact(s) sent");
      sendEvent("sent", { message_id: messageId, to: jid, type: "contact", timestamp });
      
      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to send contact");
      throw err;
    }
  },

  // Chat Operations

  async archive_chat(params) {
    const { chat_jid, archive } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(chat_jid);

    try {
      await sock.chatModify({ archive: archive !== false }, jid);
      logger.info({ jid, archived: archive !== false }, "Chat archived/unarchived");
      return { status: "updated", chat_jid: jid, archived: archive !== false };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to archive chat");
      throw err;
    }
  },

  async block_user(params) {
    const { jid, block } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const userJid = toJid(jid);

    try {
      if (block) {
        await sock.updateBlockStatus(userJid, "block");
        logger.info({ jid: userJid }, "User blocked");
        return { status: "blocked", jid: userJid };
      } else {
        await sock.updateBlockStatus(userJid, "unblock");
        logger.info({ jid: userJid }, "User unblocked");
        return { status: "unblocked", jid: userJid };
      }
    } catch (err) {
      logger.error({ err: err.message, jid: userJid }, "Failed to update block status");
      throw err;
    }
  },

  async edit_message(params) {
    const { to, message_id, text, from_me } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const result = await sock.sendMessage(jid, {
        text: text,
        edit: {
          remoteJid: jid,
          id: message_id,
          fromMe: from_me ?? true,
        },
      });

      const messageId = result?.key?.id || message_id;
      logger.info({ jid, messageId }, "Message edited");
      
      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to edit message");
      throw err;
    }
  },

  // Profile Operations

  async update_profile_name(params) {
    const { name } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      await sock.updateProfileName(name);
      logger.info({ name }, "Profile name updated");
      return { status: "updated", name };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to update profile name");
      throw err;
    }
  },

  async update_profile_status(params) {
    const { status } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      await sock.updateProfileStatus(status);
      logger.info({ status }, "Profile status updated");
      return { status: "updated" };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to update profile status");
      throw err;
    }
  },

  async update_profile_picture(params) {
    const { image_url } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const buffer = fs.readFileSync(image_url);
      await sock.updateProfilePicture(selfInfo?.jid, buffer);
      logger.info("Profile picture updated");
      return { status: "updated" };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to update profile picture");
      throw err;
    }
  },

  async remove_profile_picture() {
    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      await sock.removeProfilePicture(selfInfo?.jid);
      logger.info("Profile picture removed");
      return { status: "removed" };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to remove profile picture");
      throw err;
    }
  },

  async get_profile(params) {
    const { jid } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const userJid = jid ? toJid(jid) : selfInfo?.jid;
      const [result] = await sock.onWhatsApp(userJid);
      
      if (result) {
        return {
          jid: result.jid,
          exists: result.exists,
        };
      }
      return { jid: userJid, exists: false };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to get profile");
      throw err;
    }
  },

  async check_whatsapp(params) {
    const { numbers } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const results = [];
      for (const number of numbers) {
        const jid = toJid(number);
        const [result] = await sock.onWhatsApp(jid);
        results.push({
          number: number,
          jid: result?.jid || null,
          exists: result?.exists || false,
        });
      }
      
      logger.info({ count: results.length }, "Checked WhatsApp numbers");
      return { results };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to check WhatsApp numbers");
      throw err;
    }
  },

  async send_sticker(params) {
    const { to, sticker, gif_playback } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const buffer = fs.readFileSync(sticker);
      const result = await sock.sendMessage(jid, {
        sticker: buffer,
        gifPlayback: gif_playback || false,
      });

      const messageId = result?.key?.id || "unknown";
      logger.info({ jid, messageId }, "Sticker sent");
      sendEvent("sent", { message_id: messageId, to: jid, type: "sticker", timestamp: Date.now() });

      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to send sticker");
      throw err;
    }
  },

  async send_buttons(params) {
    const { to, title, description, buttons, footer, thumbnail_url } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const buttonMessage = {
        text: description || title,
        footer: footer || undefined,
        buttons: buttons.map((btn, idx) => ({
          buttonId: btn.id || `btn_${idx}`,
          buttonText: { displayText: btn.text },
          type: 1,
        })),
        headerType: 1,
      };

      if (thumbnail_url) {
        buttonMessage.image = { url: thumbnail_url };
        buttonMessage.caption = description || title;
        buttonMessage.headerType = 4;
      }

      const result = await sock.sendMessage(jid, buttonMessage);
      const messageId = result?.key?.id || "unknown";
      logger.info({ jid, messageId, buttonCount: buttons.length }, "Buttons sent");
      sendEvent("sent", { message_id: messageId, to: jid, type: "buttons", timestamp: Date.now() });

      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to send buttons");
      throw err;
    }
  },

  async send_list(params) {
    const { to, title, description, button_text, sections, footer } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    const jid = toJid(to);

    try {
      const listMessage = {
        text: description || title,
        footer: footer || undefined,
        title: title,
        buttonText: button_text || "Options",
        sections: sections.map((section) => ({
          title: section.title,
          rows: section.rows.map((row, idx) => ({
            title: row.title,
            description: row.description || "",
            rowId: row.id || `row_${idx}`,
          })),
        })),
      };

      const result = await sock.sendMessage(jid, {
        listMessage,
      });

      const messageId = result?.key?.id || "unknown";
      logger.info({ jid, messageId, sectionCount: sections.length }, "List sent");
      sendEvent("sent", { message_id: messageId, to: jid, type: "list", timestamp: Date.now() });

      return { message_id: messageId, to: jid };
    } catch (err) {
      logger.error({ err: err.message, jid }, "Failed to send list");
      throw err;
    }
  },

  async send_status(params) {
    const { type, content, caption, background_color, font, status_jid_list, all_contacts } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      let message = {};
      const targetJids = all_contacts ? await getAllContactJids() : (status_jid_list || []);

      if (type === "text") {
        message = {
          text: content,
          backgroundColor: background_color || "#25D366",
          font: font || 0,
        };
      } else if (type === "image" || type === "video") {
        const buffer = fs.readFileSync(content);
        message = {
          [type]: buffer,
          caption: caption || undefined,
        };
      } else if (type === "audio") {
        const buffer = fs.readFileSync(content);
        message = {
          audio: buffer,
          ptt: true,
        };
      }

      const result = await sock.sendMessage("status@broadcast", message, {
        statusJidList: targetJids.length > 0 ? targetJids : undefined,
      });

      const messageId = result?.key?.id || "unknown";
      logger.info({ messageId, type, recipientCount: targetJids.length }, "Status sent");
      sendEvent("sent", { message_id: messageId, to: "status@broadcast", type: "status", timestamp: Date.now() });

      return { message_id: messageId, type, recipients: targetJids.length };
    } catch (err) {
      logger.error({ err: err.message, type }, "Failed to send status");
      throw err;
    }
  },

  async fetch_privacy_settings() {
    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const privacy = await sock.fetchPrivacySettings();
      logger.info("Fetched privacy settings");
      return {
        readreceipts: privacy?.readreceipts || "all",
        profile: privacy?.profile || "all",
        status: privacy?.status || "all",
        online: privacy?.online || "all",
        last: privacy?.last || "all",
        groupadd: privacy?.groupadd || "all",
      };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to fetch privacy settings");
      throw err;
    }
  },

  async update_privacy_settings(params) {
    const { readreceipts, profile, status, online, last, groupadd } = params;

    if (!sock || connectionState !== "connected") {
      throw new Error("Not connected to WhatsApp");
    }

    try {
      const updates = {};
      if (readreceipts) updates.readreceipts = readreceipts;
      if (profile) updates.profile = profile;
      if (status) updates.status = status;
      if (online) updates.online = online;
      if (last) updates.last = last;
      if (groupadd) updates.groupadd = groupadd;

      await sock.updatePrivacySettings(updates);
      logger.info({ updates }, "Updated privacy settings");
      return { status: "updated", ...updates };
    } catch (err) {
      logger.error({ err: err.message }, "Failed to update privacy settings");
      throw err;
    }
  },

  async get_settings() {
    return {
      reject_call: instanceSettings.reject_call || false,
      msg_call: instanceSettings.msg_call || "",
      groups_ignore: instanceSettings.groups_ignore || false,
      always_online: instanceSettings.always_online || false,
      read_messages: instanceSettings.read_messages || false,
      read_status: instanceSettings.read_status || false,
      sync_full_history: instanceSettings.sync_full_history || false,
    };
  },

  async update_settings(params) {
    const { reject_call, msg_call, groups_ignore, always_online, read_messages, read_status, sync_full_history } = params;

    if (reject_call !== undefined) instanceSettings.reject_call = reject_call;
    if (msg_call !== undefined) instanceSettings.msg_call = msg_call;
    if (groups_ignore !== undefined) instanceSettings.groups_ignore = groups_ignore;
    if (always_online !== undefined) instanceSettings.always_online = always_online;
    if (read_messages !== undefined) instanceSettings.read_messages = read_messages;
    if (read_status !== undefined) instanceSettings.read_status = read_status;
    if (sync_full_history !== undefined) instanceSettings.sync_full_history = sync_full_history;

    logger.info({ settings: instanceSettings }, "Updated instance settings");

    return {
      reject_call: instanceSettings.reject_call || false,
      msg_call: instanceSettings.msg_call || "",
      groups_ignore: instanceSettings.groups_ignore || false,
      always_online: instanceSettings.always_online || false,
      read_messages: instanceSettings.read_messages || false,
      read_status: instanceSettings.read_status || false,
      sync_full_history: instanceSettings.sync_full_history || false,
    };
  },
};

async function getAllContactJids() {
  const jids = [];
  if (sock.store && sock.store.contacts) {
    for (const [jid] of sock.store.contacts) {
      if (jid && !jid.endsWith("@broadcast") && jid !== "status@broadcast" && !isJidGroup(jid)) {
        jids.push(jid);
      }
    }
  }
  return jids;
}

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
