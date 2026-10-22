"""Rutas de la API móvil. Se montan bajo /api/v1/ en vivasoccer/urls.py."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("token/", views.LoginView.as_view(), name="api_token"),
    path("token/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path("activar/", views.ActivarView.as_view(), name="api_activar"),
    # Entrenador
    path("mis-grupos/", views.MisGruposView.as_view(), name="api_mis_grupos"),
    path("alumnos/", views.AlumnosView.as_view(), name="api_alumnos"),
    path(
        "alumnos/<int:pk>/evaluaciones/",
        views.HistorialView.as_view(),
        name="api_historial",
    ),
    path("evaluaciones/", views.EvaluacionesView.as_view(), name="api_evaluaciones"),
    path(
        "evaluaciones/<int:pk>/",
        views.EvaluacionDetalleView.as_view(),
        name="api_evaluacion",
    ),
]
