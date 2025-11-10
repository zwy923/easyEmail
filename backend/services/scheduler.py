"""定时任务调度"""
from celery.schedules import crontab
from backend.celery_worker import celery_app
from backend.config import settings
from backend.utils.logging_config import log


def setup_periodic_tasks():
    """设置定时任务"""
    # 每5分钟检查一次新邮件
    celery_app.conf.beat_schedule = {
        'check-emails-every-5-minutes': {
            'task': 'backend.tasks.email_tasks.check_all_accounts',
            'schedule': crontab(minute='*/5'),  # 每5分钟
        },
    }
    
    log.info("定时任务已配置：每5分钟检查新邮件")


# 初始化定时任务
setup_periodic_tasks()

