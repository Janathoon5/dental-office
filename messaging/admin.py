from django.contrib import admin
from dental_office.mixins import SoftDeleteAdminMixin
from .models import Conversation, Message, DeviceToken


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ['sender', 'body', 'sent_at', 'read_at']
    readonly_fields = ['sent_at']


@admin.register(Conversation)
class ConversationAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'created_at', 'is_active']
    search_fields = ['patient__first_name', 'patient__last_name']
    inlines = [MessageInline]


@admin.register(DeviceToken)
class DeviceTokenAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'platform', 'created_at', 'is_active']
    list_filter = ['platform']
    search_fields = ['patient__first_name', 'patient__last_name']
