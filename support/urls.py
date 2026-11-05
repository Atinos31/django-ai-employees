from django.urls import path

from . import dashboard_views, views

urlpatterns = [
    path('chat/<int:order_id>/', views.chat, name="chat"),

    # Staff dashboard
    path('dashboard/', dashboard_views.dashboard, name="support_dashboard"),
    path('dashboard/<int:conversation_id>/', dashboard_views.conversation_detail, name="support_conversation"),
    path('dashboard/stream/', dashboard_views.stream, name="support_stream"),
    path('dashboard/events/', dashboard_views.events, name="support_events"),
]
