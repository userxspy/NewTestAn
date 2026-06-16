from aiohttp import web
from web.login_routes import login_routes
from web.dashboard_routes import dashboard_routes
from web.stats_routes import stats_routes
from web.profile_routes import profile_routes

# एक मास्टर राउट टेबल डिफाइन करें
admin_routes = web.RouteTableDef()

def register_admin_components(app: web.Application):
    """सारे अलग-अलग फाइलों के रूट्स को सिंगल सर्वर इंजन में सिंक करने की मास्टर पाइपलाइन"""
    app.add_routes(login_routes)
    app.add_routes(dashboard_routes)
    app.add_routes(stats_routes)
    app.add_routes(profile_routes)
    app.add_routes(admin_routes)
