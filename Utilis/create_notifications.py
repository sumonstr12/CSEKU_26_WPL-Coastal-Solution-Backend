
import os
from custom_admin.models import *


def create_notification(title, content, users):
    if not isinstance(users, list):
        users = [users]

    notification = Notification.objects.create(
        title=title,
        content=content
    )

    if len(users) == 1:
        UserNotification.objects.create(
            user=users[0],
            notification=notification
        )
    else:
        user_notifications = [
            UserNotification(user=user, notification=notification)
            for user in users
        ]
        UserNotification.objects.bulk_create(user_notifications)

    return notification
