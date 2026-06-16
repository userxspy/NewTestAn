import io
import os
import re
import json
import time
import hmac
import hashlib
import asyncio
import logging
import urllib.parse
from collections import OrderedDict
from aiohttp import web

# कस्टमाइज्ड कोर यूटिल्स और कन्फर्म कंट्रोल्स इम्पोर्ट्स
from utils import temp, get_size, is_rate_limited, is_premium
# info.py से आवश्यक वेरिएबल्स इम्पोर्ट सिंक किए गए
from info import BIN_CHANNEL, ADMINS, BOT_TOKEN, MAX_WEB_RESULTS, MAX_THUMB_CACHE, IS_PREMIUM, USE_CAPTION_FILTER
from database.ia_filterdb import COLLECTIONS, get_search_results
from database.users_chats_db import db

logger = logging.getLogger(__name__)

search_routes = web.RouteTableDef()

# ─────────────────────────────────────────────────────────
# 📸 TRUE LRU THUMBNAIL STORAGE & CONCURRENCY SYSTEM
# ─────────────────────────────────────────────────────────
MAX_CACHE = MAX_THUMB_CACHE

# ✅ FIX 1: Semaphore 5 → 15 (ज्यादा concurrent thumb fetch)
thumb_semaphore = asyncio.Semaphore(15)

# ✅ FIX 2: अब cache में file_id नहीं, actual bytes स्टोर होंगे
#           Cache HIT पर Telegram call जीरो — instant delivery
thumb_cache = OrderedDict()  # {cache_key: bytes | "NO_THUMB"}

# डुप्लीकेट थंबनेल फेच रेस कंडीशन को रोकने के लिए Lock रजिस्ट्री
thumb_locks = {}

# इन-मेमोरी सर्च कैशे को अनकैप्ड बढ़ने से रोकने के लिए True LRU बाउंडेड कैशे
PREFETCH_CACHE = OrderedDict()  # {'user_id_query_col_mode_offset': (docs, next_offset)}
TRENDING_CACHE = OrderedDict()  # {'col_mode_query': {'results': [...], 'next_offset': '...', 'expiry': timestamp}}
TRENDING_CACHE_TTL = 300


# ─────────────────────────────────────────────────────────
# 📸 OPTIMIZED THUMBNAIL ENGINE (Bytes-in-RAM True LRU)
# ─────────────────────────────────────────────────────────
async def _get_or_fetch_thumb(fid, col_name="primary", is_retry=False):
    """
    ✅ OPTIMIZED:
      - Cache में bytes स्टोर होते हैं (file_id नहीं)
      - Cache HIT → Telegram call शून्य, instant bytes return
      - sleep(0.2) हटाया — बेवजह 200ms delay खत्म
      - Eviction: 25% bulk wipe → सिर्फ 1 item (cache thrashing बंद)
      - Semaphore: 5 → 15 (concurrent fetch capacity बढ़ी)
    """
    cache_key = f"{col_name}:{fid}"

    # ✅ Retry mode: सिर्फ "NO_THUMB" entry को invalidate करो
    if is_retry:
        if thumb_cache.get(cache_key) == "NO_THUMB":
            thumb_cache.pop(cache_key, None)

    # ✅ FIX 2 (CORE): Cache HIT → bytes directly return, Telegram call नहीं
    if cache_key in thumb_cache:
        thumb_cache.move_to_end(cache_key)  # True LRU update
        cached_val = thumb_cache[cache_key]
        return None if cached_val == "NO_THUMB" else cached_val

    # Race condition guard: same key पर duplicate fetch रोको
    lock = thumb_locks.setdefault(cache_key, asyncio.Lock())

    try:
        async with lock:
            # Double-check: lock wait के दौरान किसी और ने भर दिया हो
            if cache_key in thumb_cache:
                thumb_cache.move_to_end(cache_key)
                cached_val = thumb_cache[cache_key]
                return None if cached_val == "NO_THUMB" else cached_val

            async def _fetch():
                # ✅ FIX 3: Bulk eviction हटाई — सिर्फ 1 oldest item हटाओ
                if len(thumb_cache) >= MAX_CACHE:
                    thumb_cache.popitem(last=False)

                target_collection = COLLECTIONS.get(col_name, COLLECTIONS["primary"])
                existing = await target_collection.find_one({"_id": fid}, {"thumb_url": 1})

                # ─── Step 1: DB में पहले से saved thumb_id है? ───
                if existing and existing.get("thumb_url", "").startswith("TG_ID:"):
                    saved_thumb_id = existing["thumb_url"].replace("TG_ID:", "")
                    try:
                        file_data = await temp.BOT.download_media(saved_thumb_id, in_memory=True)
                        if file_data:
                            img_bytes = file_data.getvalue()
                            # ✅ bytes cache में store (file_id नहीं)
                            thumb_cache[cache_key] = img_bytes
                            return img_bytes
                    except Exception:
                        # Stale ID — नीचे Telegram से fresh fetch करेंगे
                        pass

                # ✅ FIX 4: sleep(0.2) हटाया — यह बेकार delay था

                # ─── Step 2: Telegram से fresh thumbnail fetch ───
                for attempt in range(5):
                    try:
                        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
                        thumb_id = None

                        if msg.video and msg.video.thumbs and len(msg.video.thumbs) > 0:
                            thumb_id = msg.video.thumbs[0].file_id
                        elif msg.document and msg.document.thumbs and len(msg.document.thumbs) > 0:
                            thumb_id = msg.document.thumbs[0].file_id

                        if thumb_id:
                            file_data = await temp.BOT.download_media(thumb_id, in_memory=True)
                            if file_data:
                                img_bytes = file_data.getvalue()
                                # ✅ bytes cache में store + DB update
                                thumb_cache[cache_key] = img_bytes
                                await target_collection.update_one(
                                    {"_id": fid},
                                    {"$set": {"thumb_url": f"TG_ID:{thumb_id}"}}
                                )
                                await db.add_to_delete_queue(BIN_CHANNEL, msg.id, 5)
                                return img_bytes
                        else:
                            # कोई thumbnail नहीं है इस file में
                            thumb_cache[cache_key] = "NO_THUMB"
                            await db.add_to_delete_queue(BIN_CHANNEL, msg.id, 5)
                            return None

                    except Exception as e:
                        err_text = str(e)
                        if "FLOOD_WAIT" in err_text or "420" in err_text:
                            match = re.search(r'wait of (\d+) second', err_text)
                            wait_time = int(match.group(1)) if match else 20
                            await asyncio.sleep(wait_time + 2)
                            continue
                        await asyncio.sleep(2)
                        continue

                return None

            async with thumb_semaphore:
                return await _fetch()

    finally:
        thumb_locks.pop(cache_key, None)


# ─────────────────────────────────────────────────────────
# 🔄 BACKGROUND PRE-FETCH WORKER (Controlled Warmup Load)
# ─────────────────────────────────────────────────────────
async def bg_prefetch_worker(tg_id, q, col, mode, prefetch_offset, lim):
    try:
        cache_key = f"{tg_id}_{q}_{col}_{mode}_{prefetch_offset}"
        if cache_key in PREFETCH_CACHE:
            return

        docs, next_off, _, _ = await get_search_results(
            q, lim, offset=prefetch_offset, collection_type=col, bypass_count=True
        )

        if docs:
            PREFETCH_CACHE[cache_key] = (docs, next_off)
            if len(PREFETCH_CACHE) > 100:
                PREFETCH_CACHE.popitem(last=False)

            logger.info(f"🔮 [PREFETCH ENGINE] Background loaded {len(docs)} results.")

            if mode != "none":
                warmup_docs = docs if tg_id in ADMINS else docs[:5]
                for doc in warmup_docs:
                    asyncio.create_task(
                        _get_or_fetch_thumb(doc["_id"], col_name=doc.get("source_col", "primary"))
                    )

    except Exception as e:
        logger.error(f"❌ Prefetch worker execution failed: {e}")


# ─────────────────────────────────────────────────────────
# 🔒 STRICT SECURITY: Telegram initData HMAC Verification
# ─────────────────────────────────────────────────────────
def verify_telegram_init_data(init_data: str) -> dict | None:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            return None
        user_str = parsed.get("user", "{}")
        return json.loads(user_str)
    except Exception:
        return None


async def get_user_role(req):
    init_data = req.headers.get("X-Telegram-Init-Data", "").strip()
    if init_data:
        user = verify_telegram_init_data(init_data)
        if user:
            tg_id = int(user.get("id", 0))
            if tg_id:
                if tg_id in ADMINS: return "admin", tg_id
                if await is_premium(tg_id): return "user", tg_id
                if not IS_PREMIUM: return "user", tg_id
        return None, None

    s_user = req.cookies.get("user_session")
    if s_user and hasattr(temp, "USER_SESSIONS"):
        session = temp.USER_SESSIONS.get(s_user, {})
        if session.get("expiry", 0) > time.time():
            tg_id = session["tg_id"]
            if tg_id in ADMINS: return "admin", tg_id
            if await is_premium(tg_id): return "user", tg_id
    return None, None


# ─────────────────────────────────────────────────────────
# 🔍 SEARCH API — Smart Pre-fetch Grid Engine
# ─────────────────────────────────────────────────────────
@search_routes.get("/api/search")
async def api_search(req):
    role, tg_id = await get_user_role(req)
    if not role:
        return web.json_response({"error": "Unauthorized Access!"}, status=403)
    if is_rate_limited(tg_id, "web_search", 1):
        return web.json_response({"error": "Spam Protection: Searching too fast!"}, status=429)

    q = req.query.get("q", "").strip()
    off = req.query.get("offset", "0")
    col = req.query.get("col", "all").lower()
    mode = req.query.get("mode", "tg").lower()

    if not q:
        return web.json_response({"results": [], "total": 0, "next_offset": ""})
    try:
        off = max(0, int(off))
    except Exception:
        off = 0

    lim = MAX_WEB_RESULTS

    if off == 0:
        trend_key = f"{col}_{mode}_{q.lower()}"
        now_ts = time.time()
        if trend_key in TRENDING_CACHE and TRENDING_CACHE[trend_key]["expiry"] > now_ts:
            cached = TRENDING_CACHE[trend_key]
            logger.info(f"🔥 [TRENDING RAM HIT] Serving payload for: {q}")

            if cached["next_offset"]:
                asyncio.create_task(bg_prefetch_worker(tg_id, q, col, mode, cached["next_offset"], lim))

            return web.json_response({
                "results": cached["results"],
                "total": off + len(cached["results"]) + (1 if cached["next_offset"] else 0),
                "next_offset": cached["next_offset"],
                "is_admin": role == "admin"
            })

    current_cache_key = f"{tg_id}_{q}_{col}_{mode}_{off}"
    all_m = []
    next_offset = ""

    if current_cache_key in PREFETCH_CACHE:
        all_m, next_offset = PREFETCH_CACHE.pop(current_cache_key)
        logger.info(f"⚡ [PREFETCH HIT] Serving Page Pipeline directly from Cache.")

    if not all_m:
        all_m, next_offset, _, _ = await get_search_results(
            q, lim, offset=off, collection_type=col, bypass_count=True
        )

    has_more = bool(next_offset)

    if has_more:
        asyncio.create_task(bg_prefetch_worker(tg_id, q, col, mode, next_offset, lim))

    results_list = []

    for d in all_m:
        fid = d.get("file_ref") or d.get("_id")
        db_id = d.get("_id")
        source_collection_name = d.get("source_col", "primary")

        if mode == "none":
            tg_thumb = ""
            poster_url = ""
        else:
            # ✅ फिक्स 1: रैंडम टाइमस्टैम्प हटाकर डेटाबेस की थंबनेल ID आधारित स्थिर/डायनेमिक साल्ट मैपिंग
            # इससे वार्मअप थंबनेल ब्राउज़र में सुपर-फास्ट लोड होंगे, और थंबनेल बदलते ही ब्राउज़र उसे तुरंत बदल देगा।
            raw_thumb = d.get("thumb_url", "")
            v_salt = raw_thumb[-8:] if (raw_thumb and raw_thumb.startswith("TG_ID:")) else "0"
            
            tg_thumb = f"/api/thumb?file_id={db_id}&col={source_collection_name}&v={v_salt}"
            poster_url = tg_thumb

        results_list.append({
            "file_id": db_id,
            "name": d.get("file_name", "Unknown File"),
            "size": get_size(d.get("file_size", 0)),
            "type": d.get("file_type", "document").upper(),
            "source": source_collection_name.capitalize(),
            "raw_collection": source_collection_name,
            "poster": poster_url,
            "tg_thumb": tg_thumb,
            "watch": f"/setup_stream?file_id={fid}&mode=watch",
            "download": f"/setup_stream?file_id={fid}&mode=download",
        })

    if off == 0 and results_list:
        trend_key = f"{col}_{mode}_{q.lower()}"
        TRENDING_CACHE[trend_key] = {
            "results": results_list,
            "next_offset": next_offset,
            "expiry": time.time() + TRENDING_CACHE_TTL
        }
        if len(TRENDING_CACHE) > 100:
            TRENDING_CACHE.popitem(last=False)

    return web.json_response({
        "results": results_list,
        "total": off + len(results_list) + (1 if has_more else 0),
        "next_offset": next_offset,
        "is_admin": role == "admin",
    })


# ─────────────────────────────────────────────────────────
# 📸 THUMBNAIL API
# ─────────────────────────────────────────────────────────
@search_routes.get("/api/thumb")
async def get_telegram_thumb(req):
    fid = req.query.get("file_id")
    col_name = req.query.get("col", "primary").lower()
    is_retry = req.query.get("retry", "false").lower() == "true"
    if not fid:
        return web.Response(status=400)

    headers = {
        "Content-Disposition": 'inline; filename="poster.jpg"',
        "Cache-Control": "max-age=86400"
    }

    # ✅ FIX 2 (ENDPOINT): अब res bytes होंगे या None — "NO_THUMB" string नहीं
    res = await _get_or_fetch_thumb(fid, col_name=col_name, is_retry=is_retry)
    if res is None:
        return web.Response(status=404)

    return web.Response(body=res, content_type="image/jpeg", headers=headers)


# ─────────────────────────────────────────────────────────
# 🎥 STREAM SETUP PIPELINE
# ─────────────────────────────────────────────────────────
@search_routes.get("/setup_stream")
async def setup_stream(req):
    role, _ = await get_user_role(req)
    if not role:
        return web.Response(text="❌ Unauthorized Access Denied!", status=403)
    fid = req.query.get("file_id")
    mode = req.query.get("mode", "watch")
    if not fid:
        return web.Response(text="❌ Missing file_id!", status=400)
    try:
        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
        await db.add_to_delete_queue(BIN_CHANNEL, msg.id, 3600)
        if mode == "watch":
            await db.track_video_play()
        return web.HTTPFound(f"/{'download' if mode == 'download' else 'watch'}/{msg.id}")
    except Exception as e:
        return web.Response(text=f"❌ Error Tunneling Stream: {e}", status=500)


@search_routes.post("/setup_stream")
async def setup_stream_post(req):
    role, _ = await get_user_role(req)
    if not role:
        return web.json_response({"error": "Unauthorized Web Access!"}, status=403)
    try:
        data = await req.json()
        fid = data.get("file_id")
        mode = data.get("mode", "watch")
    except Exception:
        fid = req.query.get("file_id")
        mode = req.query.get("mode", "watch")
    if not fid:
        return web.json_response({"error": "Missing file_id!"}, status=400)
    try:
        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
        await db.add_to_delete_queue(BIN_CHANNEL, msg.id, 3600)
        if mode == "watch":
            await db.track_video_play()
        return web.json_response({"url": f"/{'download' if mode == 'download' else 'watch'}/{msg.id}"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────
# ⚙️ ADMIN CONTROLS: EDIT & WIPE PIPELINE
# ─────────────────────────────────────────────────────────
@search_routes.post("/api/delete")
async def api_delete(req):
    role, _ = await get_user_role(req)
    if role != "admin":
        return web.json_response({"error": "Core Admin Authorization Required!"}, status=403)
    try:
        data = await req.json()
        fid = data.get("file_id")
        col = data.get("collection", "primary").lower()
        if col not in COLLECTIONS:
            return web.json_response({"error": "Invalid target collection!"}, status=400)
        res = await COLLECTIONS[col].delete_one({"_id": fid})
        return web.json_response({"success": bool(res.deleted_count)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@search_routes.post("/api/edit_name")
async def api_edit_name(req):
    role, _ = await get_user_role(req)
    if role != "admin":
        return web.json_response({"error": "Core Admin Authorization Required!"}, status=403)
    try:
        data = await req.json()
        fid = data.get("file_id")
        col = data.get("collection", "primary").lower()
        new_name = data.get("new_name", "").strip()
        if not fid or col not in COLLECTIONS or not new_name:
            return web.json_response({"error": "Missing structural inputs!"}, status=400)

        update_fields = {"file_name": new_name}
        if USE_CAPTION_FILTER:
            update_fields["caption"] = new_name

        res = await COLLECTIONS[col].update_one({"_id": fid}, {"$set": update_fields})
        
        # ✅ फिक्स 2: नाम एडिट होने पर सर्वर का पुराना सर्च कैशे क्लियर करें
        PREFETCH_CACHE.clear()
        TRENDING_CACHE.clear()

        return web.json_response({"success": bool(res.modified_count)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────
# 📥 NATIVE THUMBNAIL UPLOAD & CACHE BUSTER API
# ─────────────────────────────────────────────────────────
@search_routes.post("/api/upload_thumb")
async def api_upload_thumb(req):
    role, _ = await get_user_role(req)
    if role != "admin":
        return web.json_response({"error": "Core Admin Authorization Required!"}, status=403)
    try:
        reader = await req.multipart()
        file_id_field, collection_field, image_bytes = None, None, None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == 'file_id':
                file_id_field = (await part.read()).decode().strip()
            elif part.name == 'collection':
                collection_field = (await part.read()).decode().strip().lower()
            elif part.name == 'image':
                image_bytes = await part.read()

        if not file_id_field or not collection_field or not image_bytes:
            return web.json_response({"error": "Missing required assets!"}, status=400)
        if collection_field not in COLLECTIONS:
            return web.json_response({"error": "Target collection missing!"}, status=400)

        # ✅ Cache से bytes entry हटाओ ताकि fresh thumb serve हो
        thumb_cache.pop(f"{collection_field}:{file_id_field}", None)

        with io.BytesIO(image_bytes) as img_buffer:
            img_buffer.name = "poster.jpg"
            msg = await temp.BOT.send_photo(chat_id=BIN_CHANNEL, photo=img_buffer)

        if not msg or not msg.photo:
            return web.json_response({"error": "Telegram Node failed!"}, status=500)

        try:
            new_thumb_id = (
                msg.photo.sizes[-1].file_id
                if hasattr(msg.photo, "sizes") and msg.photo.sizes
                else msg.photo.file_id
            )
        except Exception:
            new_thumb_id = msg.photo.file_id

        db_save_value = f"TG_ID:{new_thumb_id}"
        await COLLECTIONS[collection_field].update_one(
            {"_id": file_id_field},
            {"$set": {"thumb_url": db_save_value}}
        )
        await db.add_to_delete_queue(BIN_CHANNEL, msg.id, 5)
        
        # ✅ फिक्स 3: नया थंबनेल अपलोड होने पर भी बैकएंड रैम कैशे पूरी तरह साफ़ करें
        PREFETCH_CACHE.clear()
        TRENDING_CACHE.clear()

        return web.json_response({"success": True})

    except Exception as e:
        logger.error(f"❌ Upload thumb endpoint crash: {e}")
        return web.json_response({"error": str(e)}, status=500)


@search_routes.get("/miniapp")
async def miniapp_page(req):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "web", "miniapp.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(base_dir, "Web", "miniapp.html")
    if not os.path.exists(html_path):
        return web.Response(text="miniapp.html page template not found.", status=404)
    return web.FileResponse(html_path)
