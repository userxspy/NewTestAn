import io, gc, time, html, re
import asyncio
import aiohttp
import orjson
from aiohttp import web
from bson.objectid import ObjectId
from utils import temp
from info import THUMBNAIL_STORAGE_CHANNEL
from database.users_chats_db import db as motor_db
from web.web_assets import build_page, get_auth, form_wrapper

post_routes = web.RouteTableDef()
posts_col = motor_db.db["Posts"]

# ─────────────────────────────────────────────────────────
# ⚡ ULTRA-FAST ORJSON DUMP FUNCTION
# ─────────────────────────────────────────────────────────
def fast_json(data):
    return orjson.dumps(data).decode('utf-8')

# ─────────────────────────────────────────────────────────
# 🛠️ ImgBB Auto-Converter Helper Functions
# ─────────────────────────────────────────────────────────
async def fetch_direct_ibb_url(session, url):
    url = url.strip()
    if not url: return None
    if "ibb.co" in url and "i.ibb.co" not in url:
        try:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    html_content = await resp.text()
                    match = re.search(r'<meta property="og:image" content="([^"]+)"', html_content)
                    if match: return match.group(1)
        except Exception: pass
    return url

async def convert_all_ibb_links(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_direct_ibb_url(session, u) for u in urls if u.strip()]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r]

# ─────────────────────────────────────────────────────────
# 🎨 SHARED POST FORM STYLES + SCRIPTS
# ─────────────────────────────────────────────────────────
POST_FORM_CSS = """
<style>
.pf-wrap { max-width: 720px; margin: 0 auto; padding: 16px 14px 40px; }
.pf-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.pf-back { color: var(--muted); text-decoration: none; font-size: 13px; font-weight: 700; display: flex; align-items: center; gap: 5px; background: var(--bg3); border: 1px solid var(--border); padding: 8px 14px; border-radius: 8px; transition: .18s; white-space: nowrap; }
.pf-back:hover { color: var(--text); border-color: var(--muted); }
.pf-title { font-size: 22px; font-weight: 900; color: var(--text); flex: 1; min-width: 0; }
.pf-section { background: var(--card); border: 1px solid var(--border); border-radius: 14px; margin-bottom: 14px; overflow: hidden; }
.pf-section.accent-border { border-color: var(--accent); }
.pf-sec-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.pf-sec-num { width: 26px; height: 26px; border-radius: 50%; background: var(--bg4); color: var(--text); font-size: 12px; font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.pf-section.accent-border .pf-sec-num { background: var(--accent); color: #fff; }
.pf-sec-label { font-size: 13px; font-weight: 800; color: var(--text); text-transform: uppercase; letter-spacing: .7px; }
.pf-sec-body { padding: 14px 16px; }
.pf-field { margin-bottom: 12px; }
.pf-field:last-child { margin-bottom: 0; }
.pf-lbl { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; margin-bottom: 6px; }
.pf-input { width: 100%; background: var(--bg); border: 1px solid var(--border); padding: 11px 13px; color: var(--text); border-radius: 8px; outline: none; font-family: inherit; font-size: 14px; transition: border-color .15s; box-sizing: border-box; }
.pf-input:focus { border-color: var(--accent); background: var(--bg2); }
textarea.pf-input { resize: vertical; min-height: 100px; line-height: 1.5; }
.pf-divider { display: flex; align-items: center; gap: 10px; margin: 10px 0; }
.pf-divider::before, .pf-divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.pf-divider span { color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: .8px; white-space: nowrap; }
.pf-file-btn { display: flex; align-items: center; gap: 10px; background: var(--bg3); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; cursor: pointer; transition: .18s; width: 100%; box-sizing: border-box; }
.pf-file-btn:hover { border-color: var(--muted); background: var(--bg4); }
.pf-file-btn-icon { font-size: 16px; flex-shrink: 0; }
.pf-file-btn-text { flex: 1; min-width: 0; }
.pf-file-btn-label { font-size: 13px; font-weight: 700; color: var(--text); }
.pf-file-btn-hint { font-size: 11px; color: var(--muted); margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pf-file-btn input[type=file] { display: none; }

/* Video Search */
.pf-search-row { display: flex; gap: 8px; }
.pf-search-row .pf-input { flex: 1; min-width: 0; margin: 0; }
.pf-search-btn { background: var(--accent); color: #fff; border: none; padding: 11px 18px; border-radius: 8px; font-weight: 800; font-size: 13px; cursor: pointer; white-space: nowrap; flex-shrink: 0; transition: .15s; }
.pf-search-btn:hover { background: var(--accent-hover); }
.pf-search-results { border: 1px solid var(--border); border-radius: 8px; max-height: 220px; overflow-y: auto; display: none; margin-top: 8px; background: var(--bg2); }
.pf-search-item { padding: 11px 13px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background .12s; }
.pf-search-item:last-child { border-bottom: none; }
.pf-search-item:hover { background: var(--bg3); }
.pf-search-item-name { font-weight: 700; font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pf-search-item-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
.pf-search-item-meta span { background: var(--bg4); padding: 2px 6px; border-radius: 4px; }

/* Selected Videos */
.pf-videos-label { font-size: 11px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; margin: 12px 0 8px; }
.pf-videos-empty { border: 1.5px dashed var(--border); border-radius: 8px; padding: 18px; text-align: center; color: var(--muted); font-size: 13px; font-weight: 600; }
#selectedVideosContainer { display: flex; flex-direction: column; gap: 10px; }
.pf-vid-card { background: var(--bg); border: 1px solid var(--accent); border-radius: 10px; overflow: hidden; }
.pf-vid-card-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: rgba(229,9,20,0.08); border-bottom: 1px solid rgba(229,9,20,0.2); }
.pf-vid-card-name { flex: 1; min-width: 0; font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pf-vid-del { background: rgba(160,8,8,0.85); color: #fff; border: none; width: 28px; height: 28px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .12s; }
.pf-vid-del:hover { background: var(--accent); }
.pf-vid-card-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }

/* Submit Button */
.pf-submit { width: 100%; background: var(--accent); color: #fff; border: none; padding: 15px; border-radius: 10px; font-weight: 800; font-size: 15px; cursor: pointer; margin-top: 6px; box-shadow: 0 6px 20px rgba(229,9,20,0.35); transition: transform .15s, box-shadow .15s; }
.pf-submit:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(229,9,20,0.45); }
.pf-submit:active { transform: scale(.97); }

/* Cover preview */
.pf-cover-preview { width: 100%; aspect-ratio: 2/3; max-height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 10px; display: block; border: 1px solid var(--border); background: var(--bg3); }

/* Live URL preview box */
.pf-url-preview-wrap { position: relative; margin-bottom: 10px; border-radius: 10px; overflow: hidden; background: var(--bg3); border: 1px solid var(--border); display: none; }
.pf-url-preview-wrap.visible { display: block; }
.pf-url-preview-img { width: 100%; max-height: 200px; object-fit: cover; display: block; transition: opacity .25s; }
.pf-url-preview-badge { position: absolute; top: 8px; left: 8px; background: rgba(34,197,94,0.9); color: #fff; font-size: 10px; font-weight: 800; padding: 3px 9px; border-radius: 20px; backdrop-filter: blur(6px); }
.pf-url-preview-badge.loading { background: rgba(0,0,0,0.7); }
.pf-url-preview-badge.error { background: rgba(229,9,20,0.85); }
.pf-url-preview-clear { position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.65); color: #fff; border: none; width: 26px; height: 26px; border-radius: 50%; cursor: pointer; font-size: 12px; font-weight: 800; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); transition: background .15s; }
.pf-url-preview-clear:hover { background: rgba(229,9,20,0.85); }

/* Screenshot URL preview strip */
.pf-ss-strip { display: flex; gap: 8px; flex-wrap: nowrap; overflow-x: auto; padding: 4px 0 8px; scrollbar-width: thin; }
.pf-ss-strip::-webkit-scrollbar { height: 4px; }
.pf-ss-strip::-webkit-scrollbar-track { background: var(--bg3); border-radius: 2px; }
.pf-ss-strip::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.pf-ss-thumb { flex-shrink: 0; width: 80px; height: 50px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border); background: var(--bg3); }

/* Error / Success */
.pf-err { background: rgba(229,9,20,0.12); border: 1px solid rgba(229,9,20,0.4); color: #ff6b6b; border-radius: 8px; padding: 11px 14px; font-size: 13px; font-weight: 600; margin-bottom: 14px; }
.pf-msg { background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.35); color: #4ade80; border-radius: 8px; padding: 11px 14px; font-size: 13px; font-weight: 600; margin-bottom: 14px; }
</style>
"""

POST_FORM_JS = """
<script>
async function searchVideosForPost() {
    const q = document.getElementById('videoSearchInput').value.trim();
    if (!q) return;
    const resDiv = document.getElementById('videoSearchResults');
    resDiv.style.display = 'block';
    resDiv.innerHTML = '<div class="pf-search-item" style="text-align:center; color:var(--muted);">Searching...</div>';
    try {
        const response = await fetch('/api/search?q=' + encodeURIComponent(q) + '&mode=none');
        const data = await response.json();
        if (!data.results || data.results.length === 0) {
            resDiv.innerHTML = '<div class="pf-search-item" style="text-align:center; color:var(--muted);">No files found.</div>';
            return;
        }
        let h = '';
        data.results.forEach(f => {
            const safeName = f.name.replace(/'/g, "\\'").replace(/"/g, "&quot;");
            const safeSize = (f.size || '').replace(/'/g, "\\'");
            h += `<div class="pf-search-item" onclick="addVideoToPost('${f.file_id}', '${safeName}')">
                <div class="pf-search-item-name">${f.name}</div>
                <div class="pf-search-item-meta"><span>${f.size || ''}</span></div>
            </div>`;
        });
        resDiv.innerHTML = h;
    } catch (e) {
        resDiv.innerHTML = '<div class="pf-search-item" style="text-align:center; color:var(--accent);">Error loading results</div>';
    }
}

document.addEventListener('click', function(e) {
    const resDiv = document.getElementById('videoSearchResults');
    if (resDiv && !resDiv.contains(e.target) && e.target.id !== 'videoSearchInput') {
        resDiv.style.display = 'none';
    }
});

function addVideoToPost(fileId, fileName) {
    document.getElementById('videoSearchResults').style.display = 'none';
    document.getElementById('videoSearchInput').value = '';
    const container = document.getElementById('selectedVideosContainer');
    const emptyNotice = container.querySelector('.pf-videos-empty');
    if (emptyNotice) emptyNotice.remove();
    const div = document.createElement('div');
    div.className = 'pf-vid-card';
    div.innerHTML = `
        <div class="pf-vid-card-head">
            <span style="font-size:14px;">🎬</span>
            <span class="pf-vid-card-name" title="${fileName}">${fileName}</span>
            <input type="hidden" name="video_id" value="${fileId}">
            <button type="button" class="pf-vid-del" onclick="this.closest('.pf-vid-card').remove(); checkEmpty();">✕</button>
        </div>
        <div class="pf-vid-card-body">
            <div>
                <div class="pf-lbl">Group / Episode Name</div>
                <input type="text" name="video_heading" placeholder="e.g. Episode 1, Movie Links, Season 2" class="pf-input" required>
            </div>
            <div>
                <div class="pf-lbl">Quality Label</div>
                <input type="text" name="video_name" placeholder="e.g. 1080p, 4K, 480p" class="pf-input" style="color:var(--accent); font-weight:800;" required>
            </div>
        </div>`;
    container.appendChild(div);
}

function checkEmpty() {
    const container = document.getElementById('selectedVideosContainer');
    if (!container.querySelector('.pf-vid-card')) {
        container.innerHTML = '<div class="pf-videos-empty">No videos added yet. Search above to add files.</div>';
    }
}

function updateFileName(input, labelId) {
    const lbl = document.getElementById(labelId);
    if (lbl) {
        if (input.files && input.files.length > 0) {
            if (input.multiple && input.files.length > 1) {
                lbl.textContent = input.files.length + ' files selected';
            } else {
                lbl.textContent = input.files[0].name;
            }
        } else {
            lbl.textContent = 'No file chosen';
        }
    }
}

/* ── LIVE COVER URL PREVIEW ── */
var _coverDebounce = null;
function onCoverUrlInput(inputId, wrapId) {
    clearTimeout(_coverDebounce);
    _coverDebounce = setTimeout(function() { triggerCoverPreview(inputId, wrapId); }, 500);
}

function triggerCoverPreview(inputId, wrapId) {
    var url = document.getElementById(inputId).value.trim();
    var wrap = document.getElementById(wrapId);
    var img  = wrap.querySelector('.pf-url-preview-img');
    var badge = wrap.querySelector('.pf-url-preview-badge');
    if (!url) { wrap.classList.remove('visible'); return; }
    wrap.classList.add('visible');
    badge.textContent = 'Loading...';
    badge.className = 'pf-url-preview-badge loading';
    img.style.opacity = '0';
    img.onload = function() {
        img.style.opacity = '1';
        badge.textContent = '✓ Preview';
        badge.className = 'pf-url-preview-badge';
    };
    img.onerror = function() {
        img.style.opacity = '0';
        badge.textContent = '✕ Cannot load image';
        badge.className = 'pf-url-preview-badge error';
    };
    img.src = url;
}

function clearCoverPreview(inputId, wrapId) {
    document.getElementById(inputId).value = '';
    document.getElementById(wrapId).classList.remove('visible');
    var img = document.getElementById(wrapId).querySelector('.pf-url-preview-img');
    if (img) img.src = '';
}

/* ── LIVE SCREENSHOT STRIP PREVIEW ── */
var _ssDebounce = null;
function onSsUrlInput() {
    clearTimeout(_ssDebounce);
    _ssDebounce = setTimeout(renderSsStrip, 600);
}

function renderSsStrip() {
    var raw = document.getElementById('screenshotUrlsInput').value.trim();
    var strip = document.getElementById('ssPreviewStrip');
    if (!strip) return;
    if (!raw) { strip.innerHTML = ''; return; }
    var lines = raw.split('\\n').map(l => l.trim()).filter(Boolean);
    strip.innerHTML = lines.map(function(u) {
        return '<img class="pf-ss-thumb" src="' + u + '" loading="lazy" onerror="this.style.opacity=\'0.2\'">';
    }).join('');
}
</script>
"""

# ─────────────────────────────────────────────────────────
# 📝 1. ADMIN ROUTE: CREATE POST WIZARD (UI)
# ─────────────────────────────────────────────────────────
@post_routes.get('/admin/create_post')
async def create_post_page(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.HTTPFound('/dashboard')

    err = req.query.get('err', '')
    msg = req.query.get('msg', '')
    err_html = f'<div class="pf-err">{html.escape(err)}</div>' if err else ''
    msg_html = f'<div class="pf-msg">{html.escape(msg)}</div>' if msg else ''

    body = POST_FORM_CSS + f'''
<div class="pf-wrap">
    <div class="pf-header">
        <a href="/posts" class="pf-back">← Posts</a>
        <div class="pf-title">Create New Post</div>
    </div>

    {err_html}{msg_html}

    <form action="/api/post/publish" method="post" enctype="multipart/form-data">

        <!-- SECTION 1-3: Basic Info -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">1</div>
                <div class="pf-sec-label">Basic Information</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-field">
                    <div class="pf-lbl">Post Title</div>
                    <input type="text" name="title" placeholder="e.g. Panchayat S03 or Pushpa 2" class="pf-input" required>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">Short Description</div>
                    <textarea name="description" placeholder="Write a short description about this post..." class="pf-input" required></textarea>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">Search Tags (comma separated)</div>
                    <input type="text" name="tags" placeholder="e.g. Action, Web Series, 2024, Hindi" class="pf-input">
                </div>
            </div>
        </div>

        <!-- SECTION 4: Cover Image -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">2</div>
                <div class="pf-sec-label">Cover Image</div>
            </div>
            <div class="pf-sec-body">
                <!-- Live preview box (hidden until URL typed) -->
                <div class="pf-url-preview-wrap" id="coverPreviewWrap">
                    <img class="pf-url-preview-img" src="" alt="">
                    <div class="pf-url-preview-badge loading">Loading...</div>
                    <button type="button" class="pf-url-preview-clear" onclick="clearCoverPreview('coverUrlInput','coverPreviewWrap')" title="Clear">✕</button>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">Paste Image URL (ibb.co or direct link)</div>
                    <input type="text" id="coverUrlInput" name="cover_url" placeholder="https://i.ibb.co/..." class="pf-input"
                        oninput="onCoverUrlInput('coverUrlInput','coverPreviewWrap')"
                        onpaste="setTimeout(function(){{onCoverUrlInput('coverUrlInput','coverPreviewWrap')}},50)">
                </div>
                <div class="pf-divider"><span>OR UPLOAD FILE</span></div>
                <label class="pf-file-btn">
                    <span class="pf-file-btn-icon">🖼️</span>
                    <span class="pf-file-btn-text">
                        <div class="pf-file-btn-label">Choose Cover Image</div>
                        <div class="pf-file-btn-hint" id="cover-file-hint">No file chosen</div>
                    </span>
                    <input type="file" name="cover_file" accept="image/*" onchange="updateFileName(this, 'cover-file-hint')">
                </label>
            </div>
        </div>

        <!-- SECTION 5: Screenshots -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">3</div>
                <div class="pf-sec-label">Screenshots</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-field">
                    <div class="pf-lbl">Paste ibb.co Links (one per line)</div>
                    <textarea id="screenshotUrlsInput" name="screenshot_urls"
                        placeholder="https://i.ibb.co/link1&#10;https://i.ibb.co/link2&#10;..."
                        class="pf-input" style="min-height:90px; white-space:pre-wrap;"
                        oninput="onSsUrlInput()" onpaste="setTimeout(onSsUrlInput,80)"></textarea>
                </div>
                <!-- Live screenshot thumbnails strip -->
                <div class="pf-ss-strip" id="ssPreviewStrip"></div>
                <div class="pf-divider"><span>AND / OR UPLOAD FILES</span></div>
                <label class="pf-file-btn">
                    <span class="pf-file-btn-icon">📸</span>
                    <span class="pf-file-btn-text">
                        <div class="pf-file-btn-label">Choose Screenshots</div>
                        <div class="pf-file-btn-hint" id="ss-file-hint">No files chosen</div>
                    </span>
                    <input type="file" name="screenshot_files" accept="image/*" multiple onchange="updateFileName(this, 'ss-file-hint')">
                </label>
            </div>
        </div>

        <!-- SECTION 6: Videos -->
        <div class="pf-section accent-border">
            <div class="pf-sec-head">
                <div class="pf-sec-num">4</div>
                <div class="pf-sec-label">Videos / Episodes</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-search-row">
                    <input type="text" id="videoSearchInput" placeholder="Search files in database..." class="pf-input"
                        onkeydown="if(event.key==='Enter'){{ event.preventDefault(); searchVideosForPost(); }}">
                    <button type="button" class="pf-search-btn" onclick="searchVideosForPost()">Search</button>
                </div>
                <div id="videoSearchResults" class="pf-search-results"></div>

                <div class="pf-videos-label">Selected Videos / Episodes</div>
                <div id="selectedVideosContainer">
                    <div class="pf-videos-empty">No videos added yet. Search above to add files.</div>
                </div>
            </div>
        </div>

        <button type="submit" class="pf-submit">Publish Post</button>
    </form>
</div>
''' + POST_FORM_JS

    return build_page("Create Post", body, "", "posts", role)


# ─────────────────────────────────────────────────────────
# ✏️ 2. ADMIN ROUTE: EDIT POST WIZARD (UI)
# ─────────────────────────────────────────────────────────
@post_routes.get('/admin/edit_post/{id}')
async def edit_post_page(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.HTTPFound('/dashboard')

    post_id = req.match_info['id']
    post = await posts_col.find_one({"_id": ObjectId(post_id)})
    if not post: return web.HTTPFound('/posts?err=Post not found')

    title_val = html.escape(post.get('title', ''))
    desc_val = html.escape(post.get('description', ''))
    tags_val = html.escape(", ".join(post.get('tags', [])))
    cover_url = post.get('cover_image', '')
    ss_urls = "\n".join(post.get('screenshots', []))

    err = req.query.get('err', '')
    msg = req.query.get('msg', '')
    err_html = f'<div class="pf-err">{html.escape(err)}</div>' if err else ''
    msg_html = f'<div class="pf-msg">{html.escape(msg)}</div>' if msg else ''

    # Build cover preview
    if cover_url.startswith("TG_ID:"):
        cover_img_src = f"/api/post/photo?id={cover_url.replace('TG_ID:', '')}"
        cover_hint = "Telegram-hosted image (current)"
    elif cover_url:
        cover_img_src = cover_url
        cover_hint = "External link (current)"
    else:
        cover_img_src = ""
        cover_hint = "No cover image set"

    cover_preview_html = f'<img src="{cover_img_src}" class="pf-cover-preview" alt="Current Cover" onerror="this.style.display=\'none\'">' if cover_img_src else ''
    cover_input_val = cover_url if not cover_url.startswith("TG_ID:") else ""
    cover_placeholder = cover_hint if cover_url.startswith("TG_ID:") else "https://i.ibb.co/..."

    # Build existing video cards
    video_cards_html = ""
    for v in post.get('videos', []):
        vid = v.get('file_id', '')
        vheading = html.escape(v.get('heading', 'Download Links'))
        vname = html.escape(v.get('custom_name', '1080p'))
        video_cards_html += f'''
        <div class="pf-vid-card">
            <div class="pf-vid-card-head">
                <span style="font-size:14px;">🎬</span>
                <span class="pf-vid-card-name">Pre-saved media file</span>
                <input type="hidden" name="video_id" value="{vid}">
                <button type="button" class="pf-vid-del" onclick="this.closest('.pf-vid-card').remove(); checkEmpty();">✕</button>
            </div>
            <div class="pf-vid-card-body">
                <div>
                    <div class="pf-lbl">Group / Episode Name</div>
                    <input type="text" name="video_heading" value="{vheading}" placeholder="e.g. Episode 1" class="pf-input" required>
                </div>
                <div>
                    <div class="pf-lbl">Quality Label</div>
                    <input type="text" name="video_name" value="{vname}" placeholder="e.g. 1080p" class="pf-input" style="color:var(--accent); font-weight:800;" required>
                </div>
            </div>
        </div>'''

    videos_container_content = video_cards_html if video_cards_html else '<div class="pf-videos-empty">No videos added yet. Search above to add files.</div>'

    body = POST_FORM_CSS + f'''
<div class="pf-wrap">
    <div class="pf-header">
        <a href="/post/{post_id}" class="pf-back">← Cancel</a>
        <div class="pf-title">Edit Post</div>
    </div>

    {err_html}{msg_html}

    <form action="/api/post/update" method="post" enctype="multipart/form-data">
        <input type="hidden" name="post_id" value="{post_id}">

        <!-- SECTION 1: Basic Info -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">1</div>
                <div class="pf-sec-label">Basic Information</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-field">
                    <div class="pf-lbl">Post Title</div>
                    <input type="text" name="title" value="{title_val}" class="pf-input" required>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">Short Description</div>
                    <textarea name="description" class="pf-input" required>{desc_val}</textarea>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">Search Tags (comma separated)</div>
                    <input type="text" name="tags" value="{tags_val}" class="pf-input">
                </div>
            </div>
        </div>

        <!-- SECTION 2: Cover Image -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">2</div>
                <div class="pf-sec-label">Cover Image</div>
            </div>
            <div class="pf-sec-body">
                {cover_preview_html}
                <!-- Live new-URL preview (shows when user types a new URL) -->
                <div class="pf-url-preview-wrap" id="coverPreviewWrap">
                    <img class="pf-url-preview-img" src="" alt="">
                    <div class="pf-url-preview-badge loading">Loading...</div>
                    <button type="button" class="pf-url-preview-clear" onclick="clearCoverPreview('coverUrlInput','coverPreviewWrap')" title="Clear">✕</button>
                </div>
                <div class="pf-field">
                    <div class="pf-lbl">New Image URL (leave blank to keep current)</div>
                    <input type="text" id="coverUrlInput" name="cover_url" value="{cover_input_val}" placeholder="{cover_placeholder}" class="pf-input"
                        oninput="onCoverUrlInput('coverUrlInput','coverPreviewWrap')"
                        onpaste="setTimeout(function(){{{{onCoverUrlInput('coverUrlInput','coverPreviewWrap')}}}},50)">
                </div>
                <div class="pf-divider"><span>OR UPLOAD NEW FILE</span></div>
                <label class="pf-file-btn">
                    <span class="pf-file-btn-icon">🖼️</span>
                    <span class="pf-file-btn-text">
                        <div class="pf-file-btn-label">Replace Cover Image</div>
                        <div class="pf-file-btn-hint" id="cover-file-hint">No file chosen</div>
                    </span>
                    <input type="file" name="cover_file" accept="image/*" onchange="updateFileName(this, 'cover-file-hint')">
                </label>
            </div>
        </div>

        <!-- SECTION 3: Screenshots -->
        <div class="pf-section">
            <div class="pf-sec-head">
                <div class="pf-sec-num">3</div>
                <div class="pf-sec-label">Screenshots</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-field">
                    <div class="pf-lbl">Image URLs (one per line)</div>
                    <textarea id="screenshotUrlsInput" name="screenshot_urls" class="pf-input"
                        style="min-height:90px; white-space:pre-wrap;"
                        oninput="onSsUrlInput()" onpaste="setTimeout(onSsUrlInput,80)">{html.escape(ss_urls)}</textarea>
                </div>
                <!-- Live screenshot thumbnails strip -->
                <div class="pf-ss-strip" id="ssPreviewStrip"></div>
                <div class="pf-divider"><span>AND / OR UPLOAD NEW FILES</span></div>
                <label class="pf-file-btn">
                    <span class="pf-file-btn-icon">📸</span>
                    <span class="pf-file-btn-text">
                        <div class="pf-file-btn-label">Add More Screenshots</div>
                        <div class="pf-file-btn-hint" id="ss-file-hint">No files chosen</div>
                    </span>
                    <input type="file" name="screenshot_files" accept="image/*" multiple onchange="updateFileName(this, 'ss-file-hint')">
                </label>
            </div>
        </div>

        <!-- SECTION 4: Videos -->
        <div class="pf-section accent-border">
            <div class="pf-sec-head">
                <div class="pf-sec-num">4</div>
                <div class="pf-sec-label">Videos / Episodes</div>
            </div>
            <div class="pf-sec-body">
                <div class="pf-search-row">
                    <input type="text" id="videoSearchInput" placeholder="Search and add more files..." class="pf-input"
                        onkeydown="if(event.key==='Enter'){{ event.preventDefault(); searchVideosForPost(); }}">
                    <button type="button" class="pf-search-btn" onclick="searchVideosForPost()">Search</button>
                </div>
                <div id="videoSearchResults" class="pf-search-results"></div>

                <div class="pf-videos-label">Current Videos / Episodes</div>
                <div id="selectedVideosContainer">
                    {videos_container_content}
                </div>
            </div>
        </div>

        <button type="submit" class="pf-submit">Save Changes</button>
    </form>
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {{
    renderSsStrip();
    var coverInput = document.getElementById('coverUrlInput');
    if (coverInput && coverInput.value.trim()) {{
        triggerCoverPreview('coverUrlInput', 'coverPreviewWrap');
    }}
}});
</script>
''' + POST_FORM_JS

    return build_page("Edit Post", body, "", "posts", role)


# ─────────────────────────────────────────────────────────
# ⚙️ 3. API: PUBLISH & UPDATE POSTS
# ─────────────────────────────────────────────────────────
async def process_multipart_post(req, action="publish"):
    reader = await req.multipart()
    post_data = {"title": "", "description": "", "cover_image": "", "screenshots": [], "videos": [], "tags": []}
    if action == "publish": post_data["created_at"] = int(time.time())
    
    screenshot_urls_raw = ""
    temp_v_ids, temp_v_headings, temp_v_names = [], [], []
    post_id = None
    
    while True:
        part = await reader.next()
        if part is None: break
        p_name = part.name
        
        if p_name == 'post_id': post_id = (await part.read()).decode().strip()
        elif p_name == 'title': post_data["title"] = (await part.read()).decode().strip()
        elif p_name == 'description': post_data["description"] = (await part.read()).decode().strip()
        elif p_name == 'tags': post_data["tags"] = [t.strip() for t in (await part.read()).decode().strip().split(",") if t.strip()]
        
        elif p_name == 'video_id': temp_v_ids.append((await part.read()).decode().strip())
        elif p_name == 'video_heading': temp_v_headings.append((await part.read()).decode().strip())
        elif p_name == 'video_name': temp_v_names.append((await part.read()).decode().strip())
        
        elif p_name == 'cover_url':
            url = (await part.read()).decode().strip()
            if url: post_data["cover_image"] = url
        elif p_name == 'cover_file' and part.filename:
            img_bytes = await part.read()
            with io.BytesIO(img_bytes) as img_buf:
                img_buf.name = "cover.jpg"
                msg = await temp.BOT.send_photo(chat_id=THUMBNAIL_STORAGE_CHANNEL, photo=img_buf)
                if msg and msg.photo:
                    tg_id = msg.photo.sizes[-1].file_id if hasattr(msg.photo, "sizes") and msg.photo.sizes else msg.photo.file_id
                    post_data["cover_image"] = f"TG_ID:{tg_id}"
        elif p_name == 'screenshot_urls': screenshot_urls_raw = (await part.read()).decode().strip()
        elif p_name == 'screenshot_files' and part.filename:
            img_bytes = await part.read()
            with io.BytesIO(img_bytes) as img_buf:
                img_buf.name = f"ss_{int(time.time())}.jpg"
                msg = await temp.BOT.send_photo(chat_id=THUMBNAIL_STORAGE_CHANNEL, photo=img_buf)
                if msg and msg.photo:
                    tg_id = msg.photo.sizes[-1].file_id if hasattr(msg.photo, "sizes") and msg.photo.sizes else msg.photo.file_id
                    post_data["screenshots"].append(f"TG_ID:{tg_id}")

    if post_data["cover_image"] and "ibb.co" in post_data["cover_image"]:
        converted_cover = await convert_all_ibb_links([post_data["cover_image"]])
        if converted_cover: post_data["cover_image"] = converted_cover[0]

    if screenshot_urls_raw:
        raw_urls = [u.strip() for u in screenshot_urls_raw.split('\n') if u.strip()]
        direct_urls = await convert_all_ibb_links(raw_urls)
        post_data["screenshots"].extend(direct_urls)
        
    for vid, vheading, vname in zip(temp_v_ids, temp_v_headings, temp_v_names):
        if vid and vname: 
            post_data["videos"].append({"file_id": vid, "heading": vheading or "Download Links", "custom_name": vname})
        
    return post_data, post_id

@post_routes.post('/api/post/publish')
async def api_publish_post(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.json_response({"error": "Unauthorized"}, status=403, dumps=fast_json)
    try:
        post_data, _ = await process_multipart_post(req, "publish")
        await posts_col.insert_one(post_data)
        return web.HTTPFound('/posts?msg=Post published successfully!')
    except Exception as e: return web.HTTPFound(f'/admin/create_post?err=Server Error: {str(e)}')

@post_routes.post('/api/post/update')
async def api_update_post(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.HTTPFound('/dashboard')
    try:
        post_data, post_id = await process_multipart_post(req, "update")
        if not post_id: return web.HTTPFound('/posts?err=Missing Post ID')
        
        if not post_data.get("cover_image"):
            old_post = await posts_col.find_one({"_id": ObjectId(post_id)})
            if old_post and old_post.get("cover_image"): post_data["cover_image"] = old_post["cover_image"]

        await posts_col.update_one({"_id": ObjectId(post_id)}, {"$set": post_data})
        return web.HTTPFound(f'/post/{post_id}?msg=Post updated successfully!')
    except Exception as e: return web.HTTPFound(f'/posts?err=Server Error: {str(e)}')

@post_routes.post('/api/post/delete')
async def api_delete_post(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.json_response({"success": False})
    try:
        data = await req.json()
        await posts_col.delete_one({"_id": ObjectId(data.get('post_id'))})
        return web.json_response({"success": True})
    except: return web.json_response({"success": False})

# ─────────────────────────────────────────────────────────
# 🖼️ 4. API: SERVE TELEGRAM IMAGES FOR POSTS
# ─────────────────────────────────────────────────────────
@post_routes.get('/api/post/photo')
async def get_post_photo(req):
    tg_id = req.query.get("id")
    if not tg_id: return web.Response(status=400)
    try:
        file_data = await temp.BOT.download_media(tg_id, in_memory=True)
        if not file_data: return web.Response(status=404)
        body_bytes = file_data.getvalue()
        file_data.close()
        return web.Response(body=body_bytes, content_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})
    except: return web.Response(status=500)
    finally: gc.collect()

# ─────────────────────────────────────────────────────────
# 🌐 5. PUBLIC ROUTE: POSTS DIRECTORY GRID
# ─────────────────────────────────────────────────────────
@post_routes.get('/posts')
async def posts_directory_page(req):
    role, _ = await get_auth(req)
    if not role: return web.HTTPFound('/login')
    
    all_posts = await posts_col.find({}).sort("created_at", -1).limit(21).to_list(length=21)
    has_next_init = len(all_posts) > 20
    all_posts = all_posts[:20]
    
    admin_btn = '''<button onclick="window.location.href='/admin/create_post'" style="background:var(--accent); color:#fff; border:none; padding:0 24px; border-radius:8px; font-weight:800; cursor:pointer; white-space:nowrap;">➕ Create</button>''' if role == 'admin' else ""
    
    search_ui = f'''<style>.dir-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }} @media(min-width: 768px) {{ .dir-grid {{ grid-template-columns: repeat(5, 1fr); gap: 20px; }} }} .search-box {{ background:var(--card); border:1px solid var(--border); padding:16px; border-radius:12px; margin-bottom:25px; box-shadow:0 4px 15px rgba(0,0,0,0.1); display:flex; gap:10px; }} .s-input {{ flex:1; background:var(--bg3); border:1px solid var(--border); padding:12px 16px; color:var(--text); border-radius:8px; outline:none; font-weight:600; font-size:14px; font-family:inherit; }} .pg-bar {{ display:flex; justify-content:center; align-items:center; gap:15px; margin-top:30px; }}</style><div class="search-box"><input type="text" id="post_q" class="s-input" placeholder="Search movies, series, posts..."><button onclick="resetPost(); searchPosts()" style="background:var(--bg4); color:var(--text); border:1px solid var(--border); padding:0 24px; border-radius:8px; font-weight:800; cursor:pointer;">Search</button>{admin_btn}</div>'''

    post_items = ""
    for p in all_posts:
        cover = p.get("cover_image", "")
        img_src = f"/api/post/photo?id={cover.replace('TG_ID:', '')}" if cover.startswith("TG_ID:") else cover
        post_items += f'''<div class="act-card card-enter" onclick="window.location.href='/post/{str(p["_id"])}'"><div style="position:relative; padding-top:135%; background:var(--bg3); overflow:hidden;"><img src="{img_src}" class="act-poster" loading="lazy"><div style="position:absolute; top:8px; left:8px; background:rgba(229,9,20,0.9); color:#fff; font-size:9px; padding:4px 8px; border-radius:4px; font-weight:800; backdrop-filter:blur(4px); z-index:2;">🎬 POST</div></div><div style="padding:12px; text-align:center;"><div style="font-size:13.5px; font-weight:800; color:var(--text); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">{html.escape(p.get("title", "Untitled"))}</div></div></div>'''
    
    initial_grid = f'<div id="post_grid_container" class="dir-grid">{post_items}</div>' if all_posts else '<div style="text-align:center; padding:60px 20px; color:var(--muted);">No posts found.</div>'

    js_logic = f'''<div class="pg-bar" id="post_pg_box" style="display:{'flex' if has_next_init else 'none'};"><button class="pg-btn" id="post_pBtn" onclick="prevPost()" disabled>Previous</button><span class="pg-info" id="post_pgInfo" style="font-weight:800;">Page 1</span><button class="pg-btn" id="post_nBtn" onclick="nextPost()">Next</button></div><script>var pOff = 0, pLim = 20, pPage = 1, pNext = {str(has_next_init).lower()}; async function searchPosts() {{ var q = document.getElementById('post_q').value.trim(); var grid = document.getElementById('post_grid_container'); grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted); font-weight:bold;">🔄 Searching Catalog...</div>'; try {{ var res = await fetch(`/api/posts/search?q=${{encodeURIComponent(q)}}&offset=${{pOff}}`); var data = await res.json(); grid.innerHTML = data.html; staggerCards(grid); pNext = data.has_next; updatePgUI(); }} catch(e) {{ grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:var(--accent);">Error loading posts!</div>'; }} }} function updatePgUI() {{ var box = document.getElementById('post_pg_box'); box.style.display = (pOff === 0 && !pNext) ? 'none' : 'flex'; document.getElementById('post_pBtn').disabled = (pOff === 0); document.getElementById('post_nBtn').disabled = !pNext; document.getElementById('post_pgInfo').innerText = 'Page ' + pPage; }} function resetPost() {{ pOff = 0; pPage = 1; }} function nextPost() {{ if(pNext) {{ pOff += pLim; pPage++; searchPosts(); window.scrollTo(0, 50); }} }} function prevPost() {{ if(pOff > 0) {{ pOff = Math.max(0, pOff - pLim); pPage--; searchPosts(); window.scrollTo(0, 50); }} }} document.getElementById('post_q').addEventListener('keydown', e => {{ if(e.key === 'Enter') {{ resetPost(); searchPosts(); }} }}); document.addEventListener("DOMContentLoaded", () => {{ var grid = document.getElementById('post_grid_container'); if(grid && typeof staggerCards === 'function') staggerCards(grid); }});</script>'''

    return build_page("Posts Catalog", f'<div class="main" style="padding-top:20px; max-width:1100px; margin:0 auto; padding-left:20px; padding-right:20px;">{search_ui}{initial_grid}{js_logic}</div>', "", "posts", role)

@post_routes.get('/api/posts/search')
async def api_posts_search(req):
    role, _ = await get_auth(req)
    if not role: return web.json_response({"html": ""}, dumps=fast_json)
    q = req.query.get("q", "").strip()
    try: offset = int(req.query.get("offset", 0))
    except: offset = 0
    lim = 20
    query = {}
    if q: 
        safe_q = re.escape(q)
        query["$or"] = [{"title": {"$regex": safe_q, "$options": "i"}}, {"tags": {"$regex": safe_q, "$options": "i"}}]
        
    docs = await posts_col.find(query).sort("created_at", -1).skip(offset).limit(lim + 1).to_list(length=lim + 1)
    has_next = len(docs) > lim
    docs = docs[:lim]
    
    if not docs: return web.json_response({"html": '<div style="grid-column:1/-1; text-align:center; color:var(--muted); padding:40px;">No posts matching your search.</div>', "has_next": False}, dumps=fast_json)
        
    html_out = ""
    for p in docs:
        cover = p.get("cover_image", "")
        img_src = f"/api/post/photo?id={cover.replace('TG_ID:', '')}" if cover.startswith("TG_ID:") else cover
        html_out += f'''<div class="act-card card-enter" onclick="window.location.href='/post/{str(p["_id"])}'"><div style="position:relative; padding-top:135%; background:var(--bg3); overflow:hidden;"><img src="{img_src}" class="act-poster" loading="lazy"><div style="position:absolute; top:8px; left:8px; background:rgba(229,9,20,0.9); color:#fff; font-size:9px; padding:4px 8px; border-radius:4px; font-weight:800; backdrop-filter:blur(4px); z-index:2;">🎬 POST</div></div><div style="padding:12px; text-align:center;"><div style="font-size:13.5px; font-weight:800; color:var(--text); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">{html.escape(p.get("title", "Untitled"))}</div></div></div>'''
            
    return web.json_response({"html": html_out, "has_next": has_next}, dumps=fast_json)

# ─────────────────────────────────────────────────────────
# 🍿 6. PUBLIC ROUTE: SINGLE POST VIEW (Episodes Grouped)
# ─────────────────────────────────────────────────────────
@post_routes.get('/post/{id}')
async def single_post_display(req):
    role, _ = await get_auth(req)
    if not role: return web.HTTPFound('/login')
    
    try:
        post = await posts_col.find_one({"_id": ObjectId(req.match_info['id'])})
        if not post: return web.Response(text="Post Not Found", status=404)
    except: return web.Response(text="Invalid ID", status=400)
    
    cover = post.get("cover_image", "")
    img_src = f"/api/post/photo?id={cover.replace('TG_ID:', '')}" if cover.startswith("TG_ID:") else cover
    
    tags_html = "".join([f'<span style="background:var(--bg3); border:1px solid var(--border); color:var(--muted); font-size:11px; padding:4px 10px; border-radius:4px; font-weight:700;">#{html.escape(t)}</span>' for t in post.get("tags", [])])
    tags_div = f'<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;">{tags_html}</div>' if tags_html else ""
    
    video_buttons = ""
    videos = post.get("videos", [])
    if not videos:
        video_buttons = '<div style="color:var(--muted); font-size:14px; font-weight:bold;">No media attached.</div>'
    else:
        grouped_vids = {}
        for v in videos:
            h = v.get("heading", "Download Links")
            if h not in grouped_vids: grouped_vids[h] = []
            grouped_vids[h].append(v)
            
        for heading, v_list in grouped_vids.items():
            video_buttons += f'''
            <div style="margin-bottom:20px; background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:15px; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
                <div style="font-size:16px; font-weight:900; color:var(--text); margin-bottom:12px; display:flex; align-items:center; gap:10px;">
                    <span style="background:var(--accent); width:5px; height:18px; border-radius:4px;"></span>
                    {html.escape(heading)}
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:10px; padding-left:15px;">'''
            
            for v in v_list:
                vid_id = v.get('file_id')
                v_name = html.escape(v.get('custom_name', 'Play'))
                video_buttons += f'<a href="/setup_stream?file_id={vid_id}&mode=watch" target="_blank" style="background:var(--card); border:1px solid var(--border); color:var(--text); font-weight:800; font-size:13px; text-decoration:none; padding:10px 20px; border-radius:6px; transition:0.2s; box-shadow:0 4px 10px rgba(0,0,0,0.2);" onmouseover="this.style.background=\'var(--accent)\'; this.style.borderColor=\'var(--accent)\'; this.style.color=\'#fff\'; this.style.transform=\'translateY(-2px)\'" onmouseout="this.style.background=\'var(--card)\'; this.style.borderColor=\'var(--border)\'; this.style.color=\'var(--text)\'; this.style.transform=\'translateY(0)\'">🎬 {v_name}</a>'
            
            video_buttons += '</div></div>'
    
    ss_html = ""
    for ss in post.get("screenshots", []):
        s_src = f"/api/post/photo?id={ss.replace('TG_ID:', '')}" if ss.startswith("TG_ID:") else ss
        ss_html += f'<div style="border:1px solid var(--border); border-radius:8px; overflow:hidden; aspect-ratio:16/9; background:var(--bg3); box-shadow:0 4px 15px rgba(0,0,0,0.2);"><img src="{s_src}" style="width:100%; height:100%; object-fit:cover; cursor:pointer; transition:0.3s;" onmouseover="this.style.transform=\'scale(1.03)\'" onmouseout="this.style.transform=\'scale(1)\'" onclick="window.open(this.src, \'_blank\')"></div>'
    
    gallery_grid = f'<h3 style="font-size:20px; font-weight:800; color:var(--text); border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:20px; margin-top:40px;">📸 Screenshots</h3><div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:20px;">{ss_html}</div>' if ss_html else ""

    admin_actions = f'''
    <div style="margin-top:30px; padding-top:20px; border-top:1px solid var(--border); display:flex; gap:10px;">
        <a href="/admin/edit_post/{str(post['_id'])}" style="background:var(--bg4); border:1px solid var(--border); color:var(--text); padding:12px 24px; border-radius:8px; font-weight:800; text-decoration:none; font-size:14px;">✏️ Edit Post</a>
        <button onclick="if(confirm('Are you sure you want to delete this post?')) {{ fetch('/api/post/delete', {{method:'POST', body:JSON.stringify({{post_id:'{str(post['_id'])}'}})}}).then(r=>r.json()).then(d=>{{ if(d.success) window.location.href='/posts'; else alert('Failed to delete'); }}) }}" style="background:rgba(160,8,8,0.8); border:1px solid rgba(229,9,20,0.5); color:#fff; padding:12px 24px; border-radius:8px; font-weight:800; cursor:pointer; font-size:14px;">🗑️ Delete</button>
    </div>
    ''' if role == 'admin' else ""

    page_body = f'''
    <div class="main" style="max-width:950px; margin:30px auto; padding:0 20px;">
        <div style="margin-bottom:20px;">
            <a href="/posts" style="color:var(--muted); text-decoration:none; font-size:14px; font-weight:800;">← Back to Catalog</a>
        </div>
        
        <div style="background:var(--card); border:1px solid var(--border); border-radius:16px; overflow:hidden; box-shadow:0 12px 40px rgba(0,0,0,0.3);">
            <div style="display:grid; grid-template-columns:200px 1fr; gap:0;">
                <div style="background:var(--bg3);">
                    <img src="{img_src}" style="width:100%; height:100%; object-fit:cover; display:block; min-height:250px;" onerror="this.style.display='none'">
                </div>
                <div style="padding:25px;">
                    <h1 style="font-size:24px; font-weight:900; color:var(--text); margin-bottom:10px; line-height:1.3;">{html.escape(post.get("title", "Untitled"))}</h1>
                    <p style="color:var(--muted); font-size:14px; line-height:1.6; margin-bottom:10px;">{html.escape(post.get("description", ""))}</p>
                    {tags_div}
                </div>
            </div>
        </div>
        
        <div style="margin-top:30px;">
            <h3 style="font-size:20px; font-weight:800; color:var(--text); border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:20px;">🎬 Download Links</h3>
            {video_buttons}
        </div>
        
        {gallery_grid}
        {admin_actions}
    </div>
    '''

    return build_page(post.get("title", "Post"), page_body, "", "posts", role)
