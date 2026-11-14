from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminAccountChangeForm, AdminAccountCreationForm
from .models import Division, StaffAccount


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name', 'division_code', 'is_active', 'created_at')
    search_fields = ('name', 'division_code')


@admin.register(StaffAccount)
class StaffAccountAdmin(UserAdmin):
    form = AdminAccountChangeForm
    add_form = AdminAccountCreationForm
    list_display = ('email', 'display_name', 'account_type', 'division', 'is_active')
    list_filter = ('account_type', 'is_active', 'division')
    search_fields = ('email', 'display_name')
    ordering = ('email',)
    readonly_fields = ('created_at', 'last_login')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Bulig account', {'fields': ('display_name', 'account_type', 'division', 'is_active')}),
        ('Django admin access', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'created_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'display_name', 'account_type', 'division', 'password1', 'password2'),
        }),
    )
