/**
 * 探索物品页 mock 数据（8 件社区闲置物品）
 * 字段：id, title, image, condition(成色), exchange_mode(交换模式), distance(距离), carbon(碳减排)
 * category_id 为附加字段，对齐后端真实分类 ID，用于筛选
 */

// Unsplash 图片统一参数：自动格式、居中裁剪、压缩
const u = (id, w = 600) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=80`

export const mockItems = [
  {
    id: 101,
    title: '复古胶片相机',
    image: u('photo-1526170375885-4d8ecf77b99f'),
    condition: '八成新',
    exchange_mode: '物物交换',
    distance: '0.8km',
    carbon: 3.2,
    category_id: 21,
  },
  {
    id: 102,
    title: '头戴式降噪耳机',
    image: u('photo-1505740420928-5e560c06d30e'),
    condition: '九成新',
    exchange_mode: '积分兑换',
    distance: '1.2km',
    carbon: 2.6,
    category_id: 21,
  },
  {
    id: 103,
    title: '九成新轻薄笔记本',
    image: u('photo-1496181133206-80ce9b88a853'),
    condition: '九成新',
    exchange_mode: '物物交换',
    distance: '2.4km',
    carbon: 12.5,
    category_id: 21,
  },
  {
    id: 104,
    title: '儿童绘本套装（8册）',
    image: u('photo-1512820790803-83ca734da794'),
    condition: '七成新',
    exchange_mode: '免费送出',
    distance: '0.5km',
    carbon: 1.8,
    category_id: 9,
  },
  {
    id: 105,
    title: '北欧布艺三人沙发',
    image: u('photo-1567538096630-e0c55bd6374c'),
    condition: '七成新',
    exchange_mode: '物物交换',
    distance: '3.1km',
    carbon: 28.0,
    category_id: 22,
  },
  {
    id: 106,
    title: '入门民谣木吉他',
    image: u('photo-1510915361894-db8b60106cb1'),
    condition: '八成新',
    exchange_mode: '积分兑换',
    distance: '1.7km',
    carbon: 4.4,
    category_id: 24,
  },
  {
    id: 107,
    title: '婴儿安抚毛绒玩具',
    image: u('photo-1519689680058-324335c77eba'),
    condition: '全新闲置',
    exchange_mode: '免费送出',
    distance: '0.9km',
    carbon: 1.1,
    category_id: 23,
  },
  {
    id: 108,
    title: '城市通勤变速自行车',
    image: u('photo-1485965120184-e220f721d03e'),
    condition: '八成新',
    exchange_mode: '物物交换',
    distance: '2.0km',
    carbon: 18.6,
    category_id: 14,
  },
]

/**
 * 图片加载失败时的默认绿色占位图（内联 SVG，无需额外文件）
 */
export const FALLBACK_IMAGE =
  'data:image/svg+xml;charset=utf-8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
      <rect width="400" height="300" fill="#E8F5E9"/>
      <g fill="none" stroke="#4CAF50" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" opacity="0.75">
        <path d="M200 218c-52 0-92-34-92-82 0-40 30-70 70-70 34 0 56 20 66 44 8-6 18-10 30-10 26 0 46 20 46 46 0 40-34 72-78 72z"/>
        <path d="M176 190c22-26 44-34 66-26"/>
      </g>
      <text x="200" y="252" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#2E7D32">图片暂时无法显示</text>
    </svg>`,
  )
