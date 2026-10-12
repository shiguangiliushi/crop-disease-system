<template>
  <van-tabbar route fixed placeholder safe-area-inset-bottom>
    <van-tabbar-item replace to="/detect" icon="photograph">{{ t('nav.detect') }}</van-tabbar-item>
    <van-tabbar-item replace to="/history" icon="records">{{ t('nav.history') }}</van-tabbar-item>
    <van-tabbar-item replace to="/mine" icon="user-o">{{ t('nav.mine') }}</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
/**
 * 底部导航（识别 / 记录 / 我的）
 * 只承载"农户日常最常用的三件事"；论坛、百科等重内容留给桌面客户端
 * （手机屏幕上信息密度不足，硬塞进来只会让人找不到重点）。
 */
import { useI18n } from '@/i18n';

const { t } = useI18n();
</script>
