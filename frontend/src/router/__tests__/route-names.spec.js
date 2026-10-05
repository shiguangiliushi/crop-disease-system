/**
 * 路由名对账自检（第 112 批）
 * ------------------------------------------------------------------
 * **为什么需要这条测试**：`router.push({ name: 'xxx' })` 里的名字写错时，
 * vue-router **不抛异常、不跳转、type-check 也不报** —— 它只往控制台打一条 warn。
 * 用户看到的现象是"点了没有任何反应"，而开发者从报错里什么都看不到。
 *
 * 真实事故（第 112 批，用户报"私信功能用不了"）：
 *   · `MessagesView.vue` 聊天头部的"看主页"按钮 → `name: 'userProfile'`
 *   · `UserProfileView.vue` 关注/粉丝列表点用户 → 同一个错名字
 *   而路由表里注册的是 **`user-profile`**（带连字符）。
 *   两处都表现为"点了没反应"：一处是弹窗关了但页面不动，一处是按钮像坏的。
 *
 * 判定方式：静态扫源码里所有 `router.push/replace({ name: '…' })`，
 * 与路由表里定义的名字集合对账。不需要挂载组件、不需要跑浏览器。
 *
 * 为什么放在单元测试里而不是 E2E：这是**静态可判定的**问题，
 * 用 E2E 抓成本高得多（要真点一遍每个按钮），而且漏一个就白搭。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = resolve(process.cwd(), 'src');
const ROUTER_FILE = join(SRC, 'router', 'index.js');

/** 递归收集 src 下的源码文件 */
function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      // 与项目惯例一致：下划线开头的目录不参与构建
      if (name.startsWith('_')) continue;
      out.push(...walk(path));
    } else if (/\.(vue|js|ts)$/.test(name)) {
      out.push(path);
    }
  }
  return out;
}

/** 路由表里定义的全部 name */
function definedRouteNames() {
  const text = readFileSync(ROUTER_FILE, 'utf8');
  const names = new Set();
  for (const match of text.matchAll(/name:\s*'([^']+)'/g)) names.add(match[1]);
  return names;
}

/**
 * 源码里所有 `router.push/replace({ ... name: '…' ... })` 的用法。
 *
 * ⚠️ 第 112 批：**必须跨行扫描**。第一版按行匹配，于是漏掉了
 * `ForumBoardView.vue` 里这种写法：
 *
 *     router.push({
 *       name: 'userProfile',     ← 与 push( 不在同一行
 *       params: { id: userId }
 *     });
 *
 * 结果那条真正有问题的跳转**没被报出来** —— 而它正是"点帖子作者名没反应"的原因。
 * 现在改成"找到 push(/replace( 之后一直读到配对的右括号"。
 *
 * 同时逐行剥掉注释：注释里提到某个错名字是在解释"应该怎么写"，
 * 不该被当成真实调用（这条也被绊过一次）。
 */
function usedRouteNames() {
  const used = [];
  for (const file of walk(SRC)) {
    if (file === ROUTER_FILE) continue;
    const raw = readFileSync(file, 'utf8');
    // 先把注释整体去掉，再扫描 —— 比逐行处理更彻底（块注释可以跨行）
    const code = raw
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .map((line) => line.replace(/\/\/.*$/, ''))
      .join('\n');

    for (const match of code.matchAll(/router\.(?:push|replace)\s*\(/g)) {
      // 从 `(` 开始找配对的右括号
      let depth = 0;
      let end = match.index + match[0].length - 1;
      for (let i = end; i < code.length; i += 1) {
        if (code[i] === '(') depth += 1;
        else if (code[i] === ')') {
          depth -= 1;
          if (depth === 0) { end = i; break; }
        }
      }
      const call = code.slice(match.index, end + 1);
      const line = code.slice(0, match.index).split('\n').length;
      for (const nameMatch of call.matchAll(/name:\s*'([^']+)'/g)) {
        used.push({ name: nameMatch[1], where: `${relative(SRC, file)}:${line}` });
      }
    }
  }
  return used;
}

describe('路由名对账（第 112 批）', () => {
  it('路由表里能读到名字（前置条件，防止测试本身失效）', () => {
    const defined = definedRouteNames();
    expect(defined.size).toBeGreaterThan(10);
    // 这两个是本次修复涉及的名字，必须在表里 —— 否则说明路由文件结构变了
    expect(defined.has('user-profile')).toBe(true);
    expect(defined.has('messages')).toBe(true);
  });

  it('源码里按名字跳转时，名字都在路由表里', () => {
    const defined = definedRouteNames();
    const used = usedRouteNames();

    // 至少要扫到一些用法，否则说明扫描逻辑坏了（假绿）
    expect(used.length).toBeGreaterThan(10);

    const invalid = used.filter((item) => !defined.has(item.name));
    expect(
      invalid,
      '下面这些 `router.push({ name })` 用了路由表里不存在的名字 —— '
      + 'vue-router 不会报错、只会打 warn，用户看到的是"点了没反应"：\n'
      + invalid.map((item) => `  ${item.name}  (${item.where})`).join('\n'),
    ).toEqual([]);
  });

  it('没有把 `user-profile` 写成驼峰的 `userProfile`（真实事故的回归）', () => {
    // 这条是上一条的特例，单独留着是因为它记录了一个**真实发生过的 bug**，
    // 而且驼峰写法看起来更"自然"，很容易再写错一次。
    // 全项目一共踩了 3 次：MessagesView（聊天头部"看主页"）、
    // UserProfileView（关注列表点人）、ForumBoardView（点帖子作者名）——
    // 三处的现象都是"点了没反应"。
    //
    // ⚠️ 用 `usedRouteNames()` 而不是全文正则：后者会被**自己的注释**绊倒
    //    （修复处的注释里写着"原来写的是 name: 'userProfile'"），第一版就栽在这。
    const offenders = usedRouteNames().filter((item) => item.name === 'userProfile');
    expect(
      offenders,
      '路由名是 `user-profile`（带连字符）。写成 `userProfile` 时 vue-router '
      + '只打 warn 不跳转，用户看到的是"点了没反应"：\n'
      + offenders.map((item) => `  ${item.where}`).join('\n'),
    ).toEqual([]);
  });
});
