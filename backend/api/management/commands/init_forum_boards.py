from django.core.management.base import BaseCommand
from api.models_forum import ForumBoard

class Command(BaseCommand):
    help = 'Initialize default forum boards'

    def handle(self, *args, **options):
        boards = [
            {
                'name': '作物病害交流',
                'description': '分享和讨论各种作物病害的症状、防治方法',
                'icon': 'bug',
                'order': 1
            },
            {
                'name': '种植技术',
                'description': '交流作物种植经验和技术',
                'icon': 'seedling',
                'order': 2
            },
            {
                'name': '农药肥料',
                'description': '讨论农药、肥料使用经验',
                'icon': 'flask',
                'order': 3
            },
            {
                'name': '农业政策',
                'description': '分享和讨论农业相关政策信息',
                'icon': 'file-contract',
                'order': 4
            },
            {
                'name': '市场行情',
                'description': '农产品市场行情交流',
                'icon': 'chart-line',
                'order': 5
            },
        ]

        for board_data in boards:
            board, created = ForumBoard.objects.get_or_create(
                name=board_data['name'],
                defaults={
                    'description': board_data['description'],
                    'icon': board_data['icon'],
                    'order': board_data['order'],
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created board: {board.name}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Board already exists: {board.name}'))
        
        self.stdout.write(self.style.SUCCESS('Successfully initialized forum boards'))
