from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from api.models import News
import random

class Command(BaseCommand):
    help = 'Adds sample news articles to the database'

    def handle(self, *args, **options):
        User = get_user_model()
        
        # Get or create a superuser for the author
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin123'
            )
            self.stdout.write(self.style.SUCCESS('Created admin user'))

        sample_news = [
            {
                'title': '2025年农作物病虫害防治新技术研讨会圆满结束',
                'content': '2025年5月15日，全国农作物病虫害防治新技术研讨会在北京成功举办。来自全国各地的农业专家、学者和从业人员齐聚一堂，共同探讨了最新的病虫害防治技术和发展趋势。会议重点讨论了生物防治、智能监测和绿色防控等前沿技术。',
                'source': '中国农业科学院',
                'is_published': True,
                'created_at': timezone.now() - timezone.timedelta(days=10)
            },
            {
                'title': '智能识别系统助力农作物病虫害精准防治',
                'content': '近日，国内首款基于深度学习的农作物病虫害智能识别系统正式上线。该系统能够识别200多种常见病虫害，准确率达95%以上，为农民提供了便捷的病虫害诊断服务。专家表示，该技术将大幅提升我国农作物病虫害防治水平。',
                'source': '农业农村部',
                'is_published': True,
                'created_at': timezone.now() - timezone.timedelta(days=5)
            },
            {
                'title': '2025年第二季度全国农作物病虫害发生趋势预测',
                'content': '根据农业农村部最新监测数据，预计2025年第二季度全国农作物病虫害总体呈中等偏重发生态势。其中，小麦赤霉病、水稻稻飞虱等病虫害在部分地区可能偏重发生。专家建议各地加强监测预警，及时采取防治措施。',
                'source': '全国农业技术推广服务中心',
                'is_published': True,
                'created_at': timezone.now() - timezone.timedelta(days=2)
            },
            {
                'title': '绿色防控技术助力农业可持续发展',
                'content': '在近日举办的绿色农业论坛上，专家指出，推广绿色防控技术是实现农业可持续发展的重要途径。通过天敌利用、生物农药等绿色防控手段，不仅可以有效控制病虫害，还能减少化学农药使用，保护生态环境。',
                'source': '中国农业科技报',
                'is_published': True,
                'created_at': timezone.now() - timezone.timedelta(days=1)
            },
            {
                'title': '智慧农业：病虫害远程诊断系统即将上线',
                'content': '由多家科研机构联合研发的农作物病虫害远程诊断系统已完成测试，预计下月正式上线。该系统整合了人工智能、大数据和物联网技术，农民只需上传作物照片，即可获得专业的病虫害诊断和防治建议。',
                'source': '农业信息化研究所',
                'is_published': True,
                'created_at': timezone.now()
            }
        ]

        for news_data in sample_news:
            news, created = News.objects.get_or_create(
                title=news_data['title'],
                defaults={
                    'content': news_data['content'],
                    'source': news_data['source'],
                    'is_published': news_data['is_published'],
                    'created_at': news_data['created_at'],
                    'author': admin_user
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully added news: {news.title}'))
            else:
                self.stdout.write(self.style.WARNING(f'News already exists: {news.title}'))

        self.stdout.write(self.style.SUCCESS('Successfully added sample news articles'))
