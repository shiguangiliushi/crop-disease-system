from django.core.management.base import BaseCommand
from api.models import PestInfo

class Command(BaseCommand):
    help = '删除不在指定列表中的病害，只保留38种指定的病害'

    def handle(self, *args, **options):
        # 指定保留的38种病害
        allowed_pests = [
            '苹果黑星病',
            '苹果黑腐病',
            '苹果雪松锈病',
            '健康苹果',
            '健康蓝莓',
            '健康樱桃',
            '樱桃白粉病',
            '玉米尾孢叶斑病',
            '玉米普通锈病',
            '健康玉米',
            '玉米北方叶枯病',
            '葡萄黑腐病',
            '葡萄黑麻疹病',
            '健康葡萄',
            '葡萄叶枯病',
            '柑橘黄龙病',
            '桃细菌性斑点病',
            '健康桃',
            '甜椒细菌性斑点病',
            '健康甜椒',
            '马铃薯早疫病',
            '健康马铃薯',
            '马铃薯晚疫病',
            '健康树莓',
            '健康大豆',
            '南瓜白粉病',
            '健康草莓',
            '草莓叶焦病',
            '番茄细菌性斑点病',
            '番茄早疫病',
            '健康番茄',
            '番茄晚疫病',
            '番茄叶霉病',
            '番茄斑枯病',
            '番茄二斑叶螨',
            '番茄靶斑病',
            '番茄花叶病毒',
            '番茄黄化曲叶病毒',
        ]

        # 获取所有病害
        all_pests = PestInfo.objects.all()
        
        # 删除不在允许列表中的病害
        deleted_count = 0
        for pest in all_pests:
            if pest.name not in allowed_pests:
                self.stdout.write(self.style.WARNING(f'删除病害: {pest.crop_type} - {pest.name}'))
                pest.delete()
                deleted_count += 1
        
        # 显示保留的病害
        remaining_pests = PestInfo.objects.all()
        self.stdout.write(self.style.SUCCESS(f'\n删除完成！共删除 {deleted_count} 条病害'))
        self.stdout.write(self.style.SUCCESS(f'保留 {remaining_pests.count()} 条病害：'))
        for pest in remaining_pests:
            self.stdout.write(f'  {pest.crop_type} - {pest.name}')
