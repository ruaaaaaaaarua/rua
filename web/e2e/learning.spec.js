import { test, expect } from '@playwright/test';

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`review persists and UI remains usable at ${viewport.width}px`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    const navigate = async name => {
      if (viewport.width < 720) await page.getByRole('button', { name: '打开导航' }).click();
      await page.locator('nav').getByRole('button', { name, exact: true }).click();
      if (viewport.width < 720) {
        await expect.poll(() => page.locator('.sidebar').evaluate(el => el.getBoundingClientRect().right))
          .toBeLessThanOrEqual(0);
      }
    };
    await navigate('复习');
    await expect(page.getByRole('heading', { name: '回到学过的地方。' })).toBeVisible();
    const group = page.locator('.review-group').filter({ hasText: `标幺值的基准选择题（${viewport.width}）` });
    await group.getByRole('button', { name: /提前练习|开始复习/ }).click();
    await expect(page.getByRole('heading', { name: '再想一次。' })).toBeVisible();
    await expect(page.getByText('模型测试解答')).toHaveCount(0);
    const submit = page.getByRole('button', { name: '提交这次答案' });
    await expect(submit).toBeDisabled();
    await info.attach('review-before-answer', { body: await page.screenshot({ fullPage: true, animations: 'disabled' }), contentType: 'image/png' });
    await page.getByRole('button', { name: /B.*选项乙/ }).click();
    await submit.click();
    await expect(page.getByRole('heading', { name: '这次答对了。' })).toBeVisible();
    await expect(page.getByText('参考答案：B')).toBeVisible();
    await page.reload();
    await navigate('复习');
    await expect(group.getByText('原题复习通过', { exact: true })).toBeVisible();
    await navigate('知识库');
    await expect(page.getByRole('button', { name: /标幺制与基准值/ }).first()).toBeVisible();
    await navigate('我的档案');
    await expect(page.locator('.archive-root')).toBeVisible();
    const geometry = await page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.width + 1);
    await info.attach('archive', { body: await page.screenshot({ fullPage: true, animations: 'disabled' }), contentType: 'image/png' });
    expect(errors).toEqual([]);
  });
}
