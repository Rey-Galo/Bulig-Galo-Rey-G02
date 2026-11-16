from django.urls import path

from . import views

app_name = 'cases'

urlpatterns = [
    path('report/', views.intake_school, name='intake_school'),
    path('report/sent/', views.intake_received, name='intake_received'),
    path('report/<uuid:school_id>/', views.intake_form, name='intake_form'),
    path('cases/', views.case_list, name='case_list'),
    path('cases/<uuid:pk>/', views.case_detail, name='case_detail'),
    path('cases/<uuid:pk>/review/', views.case_review, name='case_review'),
    path('cases/<uuid:pk>/acknowledge/', views.case_acknowledge, name='case_acknowledge'),
    path('cases/<uuid:pk>/status/', views.case_status, name='case_status'),
    path('cases/<uuid:pk>/reassign/', views.case_reassign, name='case_reassign'),
]
