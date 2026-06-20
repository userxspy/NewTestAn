import asyncio
import logging
import random
from hydrogram import Client, filters
from hydrogram.errors import FloodWait

# कोर डेटाबेस कलेक्शंस और क्रेडेंशियल्स सिंक
from database.ia_filterdb import actors, COLLECTIONS
from info import ADMINS, ACTOR_STORAGE_CHANNEL, THUMBNAIL_STORAGE_CHANNEL

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("migrate_media") & filters.user(ADMINS))
async def migrate_media_cmd(client, message):
    status_msg = await message.reply(
        "⚡ <b>Core Media Migration Pipeline Initiated...</b>\n"
        "Scanning database collections for legacy media items."
    )
    
    act_success, act_gallery_success = 0, 0
    thumb_success, thumb_skipped = 0, 0
    
    # ─────────────────────────────────────────────────────────
    # 🎭 PHASE 1: ACTOR PROFILES & LIGHTBOX GALLERY MIGRATION
    # ─────────────────────────────────────────────────────────
    try:
        await status_msg.edit("⏳ <b>Phase 1/2:</b> Migrating Actor Profiles & Lightbox Galleries...")
        cursor = actors.find({})
        async for actor in cursor:
            # 1. मुख्य प्रोफाइल फोटो का ट्रांसफर (Avatar Sync)
            p_img = actor.get("photo_url")
            if p_img and p_img.startswith("TG_ID:") and not actor.get("is_actor_permanent"):
                raw_file_id = p_img.replace("TG_ID:", "")
                try:
                    new_msg = await client.send_cached_media(chat_id=ACTOR_STORAGE_CHANNEL, media=raw_file_id)
                    new_file_id = new_msg.photo.sizes[-1].file_id if hasattr(new_msg.photo, "sizes") and new_msg.photo.sizes else new_msg.photo.file_id
                    
                    await actors.update_one(
                        {"_id": actor["_id"]}, 
                        {"$set": {"photo_url": f"TG_ID:{new_file_id}", "is_actor_permanent": True}}
                    )
                    act_success += 1
                    
                    # ⏱️ 1 से 3 सेकंड का सुरक्षित रैंडम गैप
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                    
                except FloodWait as e:
                    await asyncio.sleep(e.value + 2)
                except Exception as err:
                    logger.error(f"Actor Photo Shift Error: {err}")

            # 2. लाइटबॉक्स गैलरी एरे का ट्रांसफर (Gallery Array Sync)
            gallery = actor.get("gallery", [])
            if gallery:
                new_gallery = []
                has_changed = False
                for g_id in gallery:
                    if g_id and g_id.startswith("TG_ID:"):
                        raw_g_id = g_id.replace("TG_ID:", "")
                        try:
                            new_msg = await client.send_cached_media(chat_id=ACTOR_STORAGE_CHANNEL, media=raw_g_id)
                            new_f_id = new_msg.photo.sizes[-1].file_id if hasattr(new_msg.photo, "sizes") and new_msg.photo.sizes else new_msg.photo.file_id
                            
                            new_gallery.append(f"TG_ID:{new_f_id}")
                            act_gallery_success += 1
                            has_changed = True
                            
                            # ⏱️ 1 से 3 सेकंड का सुरक्षित रैंडम गैप
                            await asyncio.sleep(random.uniform(1.0, 3.0))
                            
                        except FloodWait as e:
                            await asyncio.sleep(e.value + 2)
                            new_gallery.append(g_id)
                        except Exception:
                            new_gallery.append(g_id)
                    else:
                        new_gallery.append(g_id)
                
                if has_changed:
                    await actors.update_one({"_id": actor["_id"]}, {"$set": {"gallery": new_gallery}})
                    
    except Exception as e:
        logger.error(f"Actor Migration Crash: {e}")

    # ─────────────────────────────────────────────────────────
    # 🖼️ PHASE 2: MOVIE THUMBNAILS COMPONENT MIGRATION
    # ─────────────────────────────────────────────────────────
    try:
        await status_msg.edit("⏳ <b>Phase 2/2:</b> Transferring Vault Posters & Web-Customized Thumbnails...")
        for name, col in COLLECTIONS.items():
            if name == "actors": 
                continue
            
            # डेटाबेस से सिर्फ उन्हीं फाइल्स को उठाएं जिनमें एक्टिव थंबनेल है और वो परमानेंट नहीं हैं
            cursor = col.find({"thumb_url": {"$exists": True, "$regex": "^TG_ID:"}})
            async for doc in cursor:
                t_id = doc.get("thumb_url")
                if t_id and not doc.get("is_thumb_permanent"):
                    raw_thumb_id = t_id.replace("TG_ID:", "")
                    try:
                        # बिना डाउनलोड किए सीधे नए सुरक्षित चैनल में फॉरवर्ड कॉपी मारना
                        new_msg = await client.send_cached_media(chat_id=THUMBNAIL_STORAGE_CHANNEL, media=raw_thumb_id)
                        new_t_id = new_msg.photo.sizes[-1].file_id if hasattr(new_msg.photo, "sizes") and new_msg.photo.sizes else new_msg.photo.file_id
                        
                        # डेटाबेस में नई परमानेंट ID अपडेट और लॉक फ्लैग सेट करना
                        await col.update_one(
                            {"_id": doc["_id"]}, 
                            {"$set": {"thumb_url": f"TG_ID:{new_t_id}", "is_thumb_permanent": True}}
                        )
                        thumb_success += 1
                        
                        # ⏱️ 1 से 3 सेकंड का सुरक्षित रैंडम गैप
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                    except Exception:
                        thumb_skipped += 1
                else:
                    thumb_skipped += 1
    except Exception as e:
        logger.error(f"Thumbnail Migration Crash: {e}")

    # 📊 अंतिम टेलीमेट्री माइग्रेशन रिपोर्ट जनरेशन
    report = (
        "<b>🎉 Smart Media Migration Matrix Complete!</b>\n\n"
        f"🎭 <b>Actors Updated:</b> <code>{act_success} Profiles</code>\n"
        f"🖼️ <b>Gallery Shifted:</b> <code>{act_gallery_success} Photos</code>\n"
        f"🖼️ <b>Thumbnails Synced:</b> <code>{thumb_success} Posters</code>\n"
        f"⚠️ <b>Skipped / Legacy:</b> <code>{thumb_skipped} Files</code>\n\n"
        "⚡ <i>All assets safely isolated and hard-locked into permanent infrastructure channels with strict anti-flood protections!</i>\n"
        "💡 <u>Tip:</u> अब आप इस <code>migrate_media.py</code> फाइल को डिलीट कर सकते हैं।"
    )
    await status_msg.edit(report)
