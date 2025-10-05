from django.urls import path
from . import views

urlpatterns = [
    path('pending-approval/', views.pending_approval, name='pending_approval'),
]