import os
from django.core.asgi import get_asgi_application

# 1. Set the settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_safety_mining.settings')

# 2. Initialize Django FIRST. 
# This must happen before any Channels or App imports!
django_asgi_app = get_asgi_application()

# 3. Import Channels and routing SECOND.
# Do NOT move these to the top of the file!
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from Analytics import routing

# 4. Define the application router
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})