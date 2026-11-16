from django.urls import path

from . import views

app_name = 'schools'

urlpatterns = [
    path('memberships/', views.membership_list, name='membership_list'),
    path('memberships/join/', views.membership_join, name='membership_join'),
    path('memberships/<uuid:pk>/edit/', views.membership_edit, name='membership_edit'),
    path('memberships/<uuid:pk>/leave/', views.membership_leave, name='membership_leave'),
]
