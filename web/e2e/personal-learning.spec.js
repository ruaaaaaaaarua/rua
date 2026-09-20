import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

test('archive exports the displayed card as a local SVG download', async ({ page }, info) => {
  await page.goto('/');
  await page.locator('nav').getByRole('button', { name: '我的档案', exact: true }).click();
  await expect(page.locator('.archive-root')).toBeVisible();
  await page.getByLabel('昵称', { exact: true }).fill('下载验证 < & >');
  await page.getByLabel('签名', { exact: true }).fill('只分享我的学习足迹');
  await page.getByRole('button', { name: '蓝图', exact: true }).click();
  const preview = await page.locator('.share-preview').innerHTML();
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载 SVG 分享卡', exact: true }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe('我的学习档案.svg');
  expect(await download.failure()).toBeNull();
  const output = info.outputPath('archive.svg');
  await download.saveAs(output);
  const svg = await readFile(output, 'utf8');
  expect(svg).toContain('下载验证 &lt; &amp; &gt;');
  expect(svg).toContain('只分享我的学习足迹');
  expect(svg).not.toContain('模型测试解答');
  expect(svg).not.toContain('<script');
  // DOM serialization can normalize SVG attributes; compare the parsed forms.
  expect(await page.evaluate(({ svg, preview }) => {
    const parser = new DOMParser();
    return parser.parseFromString(svg, 'image/svg+xml').documentElement.isEqualNode(
      parser.parseFromString(preview, 'image/svg+xml').documentElement);
  }, { svg, preview })).toBe(true);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await expect(page.locator('.archive-root')).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath(`archive-${width}.png`), fullPage: true, animations: 'disabled' });
  }
});
