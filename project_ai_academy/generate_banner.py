"""
YouTube Anime-Style Premium Banner Generator
Channel: AIとおっさん
Size: 2560x1440px
Font: Zen Maru Gothic
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import random
import os
import colorsys
import struct

WIDTH, HEIGHT = 2560, 1440

# --- Perlin Noise for clouds ---
def fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)

def lerp(a, b, t):
    return a + t * (b - a)

def gradient_1d(h, x, y):
    vectors = [(1,1),(-1,1),(1,-1),(-1,-1),(1,0),(-1,0),(0,1),(0,-1)]
    v = vectors[h % 8]
    return v[0]*x + v[1]*y

class PerlinNoise:
    def __init__(self, seed=0):
        random.seed(seed)
        self.p = list(range(256))
        random.shuffle(self.p)
        self.p = self.p + self.p
    
    def noise(self, x, y):
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        x -= math.floor(x)
        y -= math.floor(y)
        u = fade(x)
        v = fade(y)
        A = self.p[X] + Y
        B = self.p[X+1] + Y
        return lerp(
            lerp(gradient_1d(self.p[A], x, y), gradient_1d(self.p[B], x-1, y), u),
            lerp(gradient_1d(self.p[A+1], x, y-1), gradient_1d(self.p[B+1], x-1, y-1), u),
            v
        )
    
    def fbm(self, x, y, octaves=6):
        value = 0
        amp = 1.0
        freq = 1.0
        for _ in range(octaves):
            value += self.noise(x * freq, y * freq) * amp
            amp *= 0.5
            freq *= 2.0
        return value

def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))

def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def create_anime_sky(width, height):
    """新海誠風のアニメ空"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    pixels = img.load()
    perlin = PerlinNoise(seed=42)
    
    # 空のカラーストップ
    sky_stops = [
        (0.00, (5, 5, 25)),
        (0.10, (10, 12, 45)),
        (0.20, (20, 20, 70)),
        (0.30, (40, 25, 90)),
        (0.40, (70, 35, 110)),
        (0.50, (120, 55, 120)),
        (0.58, (180, 80, 105)),
        (0.63, (220, 120, 80)),
        (0.67, (240, 160, 70)),
        (0.70, (250, 180, 90)),
        (0.73, (220, 130, 85)),
        (0.78, (160, 70, 90)),
        (0.85, (60, 30, 55)),
        (0.92, (20, 15, 35)),
        (1.00, (8, 6, 18)),
    ]
    
    for y in range(height):
        ratio = y / height
        
        # ベースカラー
        base_color = sky_stops[0][1]
        for i in range(len(sky_stops) - 1):
            if sky_stops[i][0] <= ratio <= sky_stops[i+1][0]:
                t = (ratio - sky_stops[i][0]) / (sky_stops[i+1][0] - sky_stops[i][0])
                t = smoothstep(t)
                base_color = lerp_color(sky_stops[i][1], sky_stops[i+1][1], t)
                break
        
        for x in range(width):
            # パーリンノイズで雲を合成
            nx = x / width * 4.0
            ny = y / height * 3.0
            cloud_val = perlin.fbm(nx + 0.5, ny + 0.5, octaves=5)
            cloud_val = (cloud_val + 1.0) / 2.0  # 0-1に正規化
            
            # 雲の強度（上の方は薄く、中間が濃く）
            cloud_intensity = 0.0
            if 0.15 < ratio < 0.65:
                ci = 1.0 - abs(ratio - 0.40) / 0.25
                cloud_intensity = max(0, ci) * 0.35
            
            # 雲の色（空の色に応じて変化）
            cloud_brightness = cloud_val * cloud_intensity
            
            # 雲が明るい場所は暖色に（夕焼けの反射）
            if ratio > 0.35:
                warm_t = min(1.0, (ratio - 0.35) / 0.30)
                cloud_color = lerp_color((200, 180, 220), (255, 200, 160), warm_t)
            else:
                cloud_color = (180, 180, 220)
            
            r = int(base_color[0] + (cloud_color[0] - base_color[0]) * cloud_brightness)
            g = int(base_color[1] + (cloud_color[1] - base_color[1]) * cloud_brightness)
            b = int(base_color[2] + (cloud_color[2] - base_color[2]) * cloud_brightness)
            
            # 大気散乱（水平方向のグロー）
            center_dist = abs(x / width - 0.5) 
            if ratio > 0.50 and ratio < 0.75:
                glow_t = (1.0 - center_dist * 1.5) * (1.0 - abs(ratio - 0.65) / 0.15) * 0.3
                glow_t = max(0, glow_t)
                r = min(255, int(r + 80 * glow_t))
                g = min(255, int(g + 50 * glow_t))
                b = min(255, int(b + 20 * glow_t))
            
            pixels[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), 255)
    
    return img

def create_anime_stars(width, height):
    """アニメ風の星（柔らかいグロー付き）"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    random.seed(77)
    
    star_region_max_y = int(height * 0.50)
    
    # 小さい星
    for _ in range(400):
        x = random.randint(0, width)
        y = random.randint(0, star_region_max_y)
        # fade out near horizon
        fade_factor = 1.0 - (y / star_region_max_y) ** 0.5
        alpha = int(random.randint(50, 180) * fade_factor)
        if alpha > 0:
            draw.point((x, y), fill=(255, 255, 255, alpha))
    
    # 中程度の星
    for _ in range(60):
        x = random.randint(0, width)
        y = random.randint(0, int(star_region_max_y * 0.8))
        fade_factor = 1.0 - (y / star_region_max_y) ** 0.5
        size = random.randint(1, 2)
        alpha = int(random.randint(120, 240) * fade_factor)
        color = random.choice([
            (255, 255, 255), (220, 230, 255), (255, 240, 220)
        ])
        if alpha > 0:
            draw.ellipse([x-size, y-size, x+size, y+size], 
                        fill=(*color, alpha))
    
    # 大きな星（十字グロー）
    for _ in range(15):
        x = random.randint(50, width - 50)
        y = random.randint(20, int(star_region_max_y * 0.6))
        fade_factor = 1.0 - (y / star_region_max_y) ** 0.5
        
        # グロー
        glow_size = random.randint(15, 35)
        for gs in range(glow_size, 0, -1):
            a = int(8 * (gs / glow_size) * fade_factor)
            if a > 0:
                draw.ellipse([x-gs, y-gs, x+gs, y+gs],
                            fill=(200, 210, 255, a))
        
        # 光条
        ray_len = random.randint(8, 25)
        for i in range(ray_len):
            a = int(max(0, (180 - i * 8)) * fade_factor)
            if a > 0:
                draw.point((x+i, y), fill=(255, 255, 255, a))
                draw.point((x-i, y), fill=(255, 255, 255, a))
                draw.point((x, y+i), fill=(255, 255, 255, a))
                draw.point((x, y-i), fill=(255, 255, 255, a))
        
        # コア
        core_a = int(255 * fade_factor)
        draw.ellipse([x-2, y-2, x+2, y+2], fill=(255, 255, 255, core_a))
    
    return layer

def create_anime_city(width, height):
    """アニメ風の都市（奥行き感のある建物群）"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    random.seed(55)
    
    horizon_y = int(height * 0.67)
    
    # --- 遠景シルエット（薄い、ぼかし） ---
    far_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    far_draw = ImageDraw.Draw(far_layer)
    x = 0
    while x < width:
        w = random.randint(10, 35)
        h = random.randint(15, 80)
        far_draw.rectangle([x, horizon_y - h, x + w, horizon_y],
                          fill=(60, 40, 75, 100))
        x += w + random.randint(0, 5)
    far_layer = far_layer.filter(ImageFilter.GaussianBlur(radius=4))
    layer = Image.alpha_composite(layer, far_layer)
    draw = ImageDraw.Draw(layer)
    
    # --- 中景（メインのビル群） ---
    mid_y = horizon_y + 15
    x = 0
    while x < width:
        w = random.randint(20, 60)
        h = random.randint(60, 220)
        # ビルの色（微妙な色彩差）
        base_r = random.randint(18, 30)
        base_g = random.randint(15, 25)
        base_b = random.randint(35, 50)
        draw.rectangle([x, mid_y - h, x + w, mid_y], 
                      fill=(base_r, base_g, base_b, 200))
        
        # 窓の光
        for wy in range(mid_y - h + 6, mid_y - 3, 7):
            for wx in range(x + 3, x + w - 3, 6):
                if random.random() > 0.35:
                    brightness = random.uniform(0.3, 1.0)
                    wc = random.choice([
                        (int(255*brightness), int(220*brightness), int(100*brightness)),
                        (int(100*brightness), int(200*brightness), int(255*brightness)),
                        (int(255*brightness), int(170*brightness), int(80*brightness)),
                        (int(180*brightness), int(160*brightness), int(255*brightness)),
                    ])
                    a = int(brightness * 200)
                    draw.rectangle([wx, wy, wx+3, wy+4], fill=(*wc, a))
        
        x += w + random.randint(1, 10)
    
    # --- 近景（手前の暗いビル） ---
    near_y = horizon_y + 50
    x = 0
    while x < width:
        w = random.randint(35, 90)
        h = random.randint(100, 320)
        draw.rectangle([x, near_y - h, x + w, near_y],
                      fill=(10, 8, 20, 230))
        
        # 窓
        for wy in range(near_y - h + 8, near_y - 5, 9):
            for wx in range(x + 4, x + w - 4, 8):
                if random.random() > 0.3:
                    brightness = random.uniform(0.4, 1.0)
                    wc = random.choice([
                        (int(255*brightness), int(230*brightness), int(120*brightness)),
                        (int(120*brightness), int(200*brightness), int(255*brightness)),
                        (int(255*brightness), int(150*brightness), int(70*brightness)),
                    ])
                    a = int(brightness * 230)
                    draw.rectangle([wx, wy, wx+4, wy+5], fill=(*wc, a))
        
        x += w + random.randint(2, 15)
    
    # --- 地面 ---
    for y in range(near_y, height):
        t = (y - near_y) / max(1, (height - near_y))
        a = int(220 + 35 * t)
        draw.line([(0, y), (width, y)], fill=(8, 6, 15, min(255, a)))
    
    return layer

def create_atmospheric_glow(width, height):
    """大気のグロー（夕焼けの光の拡散）"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    
    # 水平グロー
    glow_y = int(height * 0.64)
    for i in range(400):
        y = glow_y - 200 + i
        t = 1.0 - abs(i - 200) / 200.0
        t = t ** 1.5
        
        # 中央が暖色、端がパープル
        for x in range(width):
            cx = abs(x / width - 0.5) * 2.0
            warm = max(0, 1.0 - cx * 1.8)
            
            r = int((180 * warm + 80 * (1-warm)) * t)
            g = int((100 * warm + 40 * (1-warm)) * t)
            b = int((60 * warm + 100 * (1-warm)) * t)
            a = int(25 * t * (1.0 - cx * 0.5))
            
            if a > 1:
                or_, og, ob, oa = layer.getpixel((x, y))
                nr = min(255, or_ + r)
                ng = min(255, og + g)
                nb = min(255, ob + b)
                na = min(255, oa + a)
                layer.putpixel((x, y), (nr, ng, nb, na))
    
    layer = layer.filter(ImageFilter.GaussianBlur(radius=15))
    return layer

def create_lens_flare(width, height):
    """レンズフレア（アニメ風の光源）"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    
    # メインフレア位置
    fx, fy = int(width * 0.5), int(height * 0.60)
    
    # ソフトグロー
    for r in range(300, 0, -1):
        t = r / 300
        alpha = int(12 * (1 - t))
        color = lerp_color((255, 200, 150), (200, 150, 220), t)
        draw.ellipse([fx-r, fy-r, fx+r, fy+r], fill=(*color, alpha))
    
    layer = layer.filter(ImageFilter.GaussianBlur(radius=20))
    return layer

def create_floating_particles(width, height):
    """浮遊する光の粒子（ホタル風）"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    random.seed(99)
    
    for _ in range(80):
        x = random.randint(0, width)
        y = random.randint(int(height * 0.20), int(height * 0.80))
        size = random.uniform(1, 3)
        
        hue = random.choice([0.10, 0.15, 0.55, 0.60, 0.80])
        r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.25, 1.0)]
        alpha = random.randint(40, 140)
        
        # ソフトグロー
        glow_r = int(size * 8)
        for gs in range(glow_r, 0, -1):
            a = int(alpha * (gs / glow_r) * 0.2)
            if a > 0:
                draw.ellipse([x-gs, y-gs, x+gs, y+gs], fill=(r, g, b, a))
        
        s = max(1, int(size))
        draw.ellipse([x-s, y-s, x+s, y+s], 
                    fill=(min(255, r+60), min(255, g+60), min(255, b+60), alpha))
    
    return layer

def render_premium_text(width, height):
    """おしゃれなフォントでテキスト描画"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    
    # Zen Maru Gothic フォント
    title_font_path = os.path.join(assets_dir, "ZenMaruGothic-Bold.ttf")
    sub_font_path = os.path.join(assets_dir, "ZenMaruGothic-Medium.ttf")
    
    if not os.path.exists(title_font_path):
        title_font_path = "C:/Windows/Fonts/YuGothB.ttc"
    if not os.path.exists(sub_font_path):
        sub_font_path = "C:/Windows/Fonts/YuGothR.ttc"
    
    title_font = ImageFont.truetype(title_font_path, 170)
    sub_font = ImageFont.truetype(sub_font_path, 54)
    
    title = "AIとおっさん"
    subtitle = "視聴者と作る、AIエンタメチャンネル"
    
    # テキストサイズ
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    
    sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_h = sub_bbox[3] - sub_bbox[1]
    
    gap = 40
    total_h = title_h + gap + sub_h
    center_y = int(height * 0.42)
    
    title_x = (width - title_w) // 2
    title_y = center_y - total_h // 2
    sub_x = (width - sub_w) // 2
    sub_y = title_y + title_h + gap
    
    # === 1. テキストの大きなグロー（オーラ） ===
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.text((title_x, title_y), title, font=title_font, 
                   fill=(180, 140, 255, 40))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=40))
    layer = Image.alpha_composite(layer, glow_layer)
    
    # === 2. テキストの中間グロー ===
    mid_glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mid_draw = ImageDraw.Draw(mid_glow)
    mid_draw.text((title_x, title_y), title, font=title_font,
                  fill=(220, 200, 255, 60))
    mid_glow = mid_glow.filter(ImageFilter.GaussianBlur(radius=15))
    layer = Image.alpha_composite(layer, mid_glow)
    
    draw = ImageDraw.Draw(layer)
    
    # === 3. ドロップシャドウ ===
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.text((title_x + 4, title_y + 6), title, font=title_font,
                     fill=(0, 0, 0, 140))
    shadow_draw.text((sub_x + 3, sub_y + 4), subtitle, font=sub_font,
                     fill=(0, 0, 0, 100))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5))
    layer = Image.alpha_composite(layer, shadow_layer)
    
    draw = ImageDraw.Draw(layer)
    
    # === 4. メインタイトル（白 + 微かなグラデーション感） ===
    draw.text((title_x, title_y), title, font=title_font,
              fill=(255, 255, 255, 255))
    
    # === 5. サブタイトル ===
    draw.text((sub_x, sub_y), subtitle, font=sub_font,
              fill=(220, 215, 240, 220))
    
    # === 6. 装飾ライン ===
    line_y = sub_y - 15
    line_half_w = 350
    cx = width // 2
    
    # メインライン
    for i in range(line_half_w):
        t = i / line_half_w
        alpha = int(120 * (1 - t ** 2))
        draw.point((cx - i, line_y), fill=(180, 200, 255, alpha))
        draw.point((cx + i, line_y), fill=(180, 200, 255, alpha))
        draw.point((cx - i, line_y + 1), fill=(140, 160, 220, alpha // 2))
        draw.point((cx + i, line_y + 1), fill=(140, 160, 220, alpha // 2))
    
    # 端のダイヤモンド装飾
    for side in [-1, 1]:
        dx = cx + side * line_half_w
        for s in range(5, 0, -1):
            a = int(80 * s / 5)
            draw.polygon([(dx, line_y-s), (dx+s, line_y), (dx, line_y+s), (dx-s, line_y)],
                        fill=(180, 200, 255, a))
    
    return layer


def main():
    print("Generating anime-style YouTube banner...")
    
    # 1. アニメ空（パーリンノイズの雲付き）
    print("  [1/7] Anime sky with clouds...")
    img = create_anime_sky(WIDTH, HEIGHT)
    
    # 2. 大気グロー
    print("  [2/7] Atmospheric glow...")
    glow = create_atmospheric_glow(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, glow)
    
    # 3. レンズフレア
    print("  [3/7] Lens flare...")
    flare = create_lens_flare(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, flare)
    
    # 4. 星空
    print("  [4/7] Star field...")
    stars = create_anime_stars(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, stars)
    
    # 5. 都市シルエット
    print("  [5/7] City silhouette...")
    city = create_anime_city(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, city)
    
    # 6. 浮遊パーティクル
    print("  [6/7] Floating particles...")
    particles = create_floating_particles(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, particles)
    
    # 7. テキスト
    print("  [7/7] Premium text rendering...")
    text = render_premium_text(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, text)
    
    # 保存
    img_final = img.convert("RGB")
    output_path = os.path.join(os.path.dirname(__file__), "assets", "youtube_banner_2560x1440.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img_final.save(output_path, "PNG")
    print(f"Banner saved: {output_path}")
    print(f"Size: {img_final.size[0]}x{img_final.size[1]}px")

if __name__ == "__main__":
    main()
