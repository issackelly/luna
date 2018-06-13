"""backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path
from backend.views import v1


urlpatterns = [
    path('api/v1/me/files', v1.file_query),
    path('api/v1/login', v1.api_login),
    re_path(r'^api/v1/get_file(?P<path>.+)', v1.get_file),
    re_path(r'^api/v1/get_thumb(?P<path>.+)', v1.get_thumb),

    path('admin/', admin.site.urls),
]
