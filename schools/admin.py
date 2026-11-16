from django.contrib import admin

from .models import School, SchoolMembership


class MembershipInline(admin.TabularInline):
    model = SchoolMembership
    extra = 0
    autocomplete_fields = ('account',)
    fields = ('account', 'role', 'is_trusted_recipient', 'is_active')


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'school_code', 'division', 'is_active')
    list_filter = ('is_active', 'division')
    search_fields = ('name', 'school_code')
    inlines = [MembershipInline]


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ('account', 'school', 'role', 'is_trusted_recipient', 'is_active')
    list_filter = ('role', 'is_trusted_recipient', 'is_active', 'school')
    search_fields = ('account__email', 'account__display_name', 'school__name')
    autocomplete_fields = ('account', 'school')
