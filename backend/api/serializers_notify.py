"""
通知与公告的序列化器（第 37 批）
"""
from rest_framework import serializers

from .models_notify import Announcement, Notification


class NotificationActorSerializer(serializers.Serializer):
    """触发人（只暴露必要的展示字段）"""
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)


class NotificationSerializer(serializers.ModelSerializer):
    actor = NotificationActorSerializer(read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'type_display', 'title', 'title_en', 'message', 'message_en', 'url',
            'actor', 'post', 'comment', 'announcement',
            'is_read', 'created_at',
        ]
        read_only_fields = fields


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_visible = serializers.BooleanField(read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'content', 'is_active', 'is_pinned',
            'expires_at', 'created_by_name', 'created_at', 'updated_at', 'is_visible',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by_name', 'is_visible']
