import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import News
from django.utils import timezone

def create_sample_news():
    # 获取或创建管理员用户
    User = get_user_model()
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@example.com',
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
    
    # 示例新闻数据 - 根据实际模型结构调整
    sample_news = [
        {
            'title': '2023年农业补贴政策解读',
            'content': '2023年国家将继续实施农业补贴政策，重点支持粮食生产、高标准农田建设、农业科技推广等领域...',
            'source': '农业农村部',
            'category': 'policy',
            'is_published': True
        },
        {
            'title': '水稻病虫害绿色防控技术指南',
            'content': '为有效防控水稻病虫害，减少化学农药使用，农业农村部组织专家制定了《水稻病虫害绿色防控技术指南》...',
            'source': '中国农业科学院',
            'category': 'tech',
            'is_published': True
        },
        {
            'title': '2023年第三季度农产品价格走势分析',
            'content': '根据农业农村部监测数据显示，2023年第三季度全国农产品批发价格指数为128.7，环比上涨2.1%，同比上涨5.3%...',
            'source': '农业农村部市场与信息化司',
            'category': 'market',
            'is_published': True
        },
        {
            'title': '2023年中国农业产业发展报告',
            'content': '《2023年中国农业产业发展报告》显示，我国农业现代化水平持续提升，粮食产量连续8年稳定在1.3万亿斤以上...',
            'source': '中国农业科学院',
            'category': 'report',
            'is_published': True
        },
        {
            'title': '关于开展2023年农业科技下乡活动的通知',
            'content': '为贯彻落实中央农村工作会议精神，加快推进农业科技进村入户，我部决定组织开展2023年农业科技下乡活动...',
            'source': '农业农村部科技教育司',
            'category': 'notice',
            'is_published': True
        },
        # 更多示例数据...
        {
            'title': '数字农业助力乡村振兴',
            'content': '近年来，数字农业技术快速发展，为乡村振兴战略实施提供了新动能...',
            'source': '中国农业信息网',
            'category': 'tech',
            'is_published': True
        },
        {
            'title': '全国农业气象周报',
            'content': '本周全国大部农区光温正常，土壤墒情适宜，利于秋收作物生长发育...',
            'source': '中国气象局',
            'category': 'market',
            'is_published': True
        },
        {
            'title': '新型农业经营主体培育计划发布',
            'content': '农业农村部发布《新型农业经营主体培育计划（2023-2025年）》...',
            'source': '农业农村部',
            'category': 'policy',
            'is_published': True
        },
        {
            'title': '农产品质量安全监测情况通报',
            'content': '2023年第二季度全国农产品质量安全例行监测总体合格率为97.8%...',
            'source': '农业农村部农产品质量安全监管司',
            'category': 'report',
            'is_published': True
        },
        {
            'title': '农业农村部部署秋粮重大病虫害防控工作',
            'content': '当前正值秋粮产量形成的关键时期，也是重大病虫害防控的攻坚期...',
            'source': '农业农村部种植业管理司',
            'category': 'notice',
            'is_published': True
        }
    ]
    
    # 添加示例新闻
    for news_data in sample_news:
        # 检查是否已存在相同标题的新闻
        if not News.objects.filter(title=news_data['title']).exists():
            News.objects.create(
                title=news_data['title'],
                content=news_data['content'],
                source=news_data['source'],
                is_published=news_data['is_published'],
                author=admin_user
            )
    
    print("示例新闻数据添加完成！")

if __name__ == "__main__":
    create_sample_news()
