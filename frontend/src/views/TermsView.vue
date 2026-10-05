<template>
  <LegalDoc
    :title="t('legal.termsTitle')"
    :subtitle="t('legal.termsSubtitle')"
    updated-at="2026-09-18"
    :sections="sections"
  />
</template>

<script setup>
/**
 * 用户协议（第 26 批新增；页脚的原「用户协议」是一个 href="#" 的死链）
 *
 * 条款内容按**本系统实际功能**撰写，不写空话：
 * 涉及识别、病害百科、行业动态、论坛交流、识别记录、用户资料等真实模块。
 * 第 71 批：正文改为按当前语言从 i18n 取，切换语言时整篇跟着变。
 */
import { computed } from 'vue';
import LegalDoc from '@/components/LegalDoc.vue';
import { tl, useI18n } from '@/i18n';

const { t } = useI18n();

const sections = computed(() => [
  {
    id: 'service',
    heading: t('legal.terms.secAServiceHeading'),
    paragraphs: tl('legal.terms.secAServiceParagraphs'),
    items: tl('legal.terms.secAServiceItems'),
  },
  {
    id: 'account',
    heading: t('legal.terms.secBAccountHeading'),
    items: tl('legal.terms.secBAccountItems'),
  },
  {
    id: 'content',
    heading: t('legal.terms.secCContentHeading'),
    paragraphs: tl('legal.terms.secCContentParagraphs'),
    items: tl('legal.terms.secCContentItems'),
  },
  {
    id: 'disclaimer',
    heading: t('legal.terms.secDDisclaimerHeading'),
    paragraphs: tl('legal.terms.secDDisclaimerParagraphs'),
  },
  {
    id: 'ip',
    heading: t('legal.terms.secEIpHeading'),
    items: tl('legal.terms.secEIpItems'),
  },
  {
    id: 'change',
    heading: t('legal.terms.secFChangeHeading'),
    items: tl('legal.terms.secFChangeItems'),
  },
  {
    id: 'update',
    heading: t('legal.terms.secGUpdateHeading'),
    paragraphs: tl('legal.terms.secGUpdateParagraphs'),
  },
  {
    id: 'contact',
    heading: t('legal.terms.secHContactHeading'),
    items: tl('legal.terms.secHContactItems'),
  },
]);
</script>
