import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from flask import Flask
from threading import Thread

# --- [Render용 Flask 서버 설정] ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    # Render는 PORT 환경 변수를 제공합니다. 없으면 8080을 사용합니다.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
# ---------------------------------

TOKEN = os.environ.get('DISCORD_TOKEN')

STAGE_ORDER = ["3-1", "3-2", "3-3", "3-4", "3-5", "3-6", "3-7", "3-8", "3-9"]

SHIP_GOALS = {
    "3-1": {"목재+": 1500, "상급 목재+": 600, "타르": 500},
    "3-2": {"목재+": 1200, "부드러운 목재": 420, "밧줄": 390},
    "3-3": {"타르": 560, "특수강괴": 300, "부드러운 목재": 300},
    "3-4": {"강철괴": 1500, "목재+": 1000, "아교": 700},
    "3-5": {"특수강괴": 240, "상급 목재+": 600, "아교": 700},
    "3-6": {"상급 목재+": 300, "마력 기폭제": 500, "튼튼 버섯 진액": 2250},
    "3-7": {"특수강괴": 300, "상급 목재+": 600, "타르": 600},
    "3-8": {"단단한 목재": 300, "두꺼운 옷감": 800, "튼튼한 밧줄": 500},
    "3-9": {"특수강괴": 450, "강철괴": 1000, "깔끔 버섯 진액": 3000}
}

DATA_FILE = 'ship_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"current_stage": "3-1", "progress": {k: {} for k in SHIP_GOALS.keys()}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 수량 입력창 (Modal) ---
class DonationModal(discord.ui.Modal):
    def __init__(self, item_name, stage, is_reservation=False):
        title = f"[{stage}] {item_name} {'예약' if is_reservation else '납품'}"
        super().__init__(title=title)
        self.item_name = item_name
        self.stage = stage
        self.is_reservation = is_reservation
        self.amount_input = discord.ui.TextInput(
            label="수량을 입력하세요",
            placeholder="숫자 입력 (차감은 -100)",
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            data = load_data()
            current_val = data["progress"][self.stage].get(self.item_name, 0)
            new_val = max(0, current_val + amount)
            data["progress"][self.stage][self.item_name] = new_val
            save_data(data)

            if self.is_reservation:
                action_text = "예약" if amount >= 0 else "예약 차감"
                emoji = "📅"
            else:
                action_text = "납품" if amount >= 0 else "납품 차감"
                emoji = "🤫"

            await interaction.response.send_message(f"✅ {self.item_name} {abs(amount)}개 처리 완료!", ephemeral=True)
            notif = f"{emoji} 누군가 **{self.stage}** 단계에 **{self.item_name}** {abs(amount)}개를 {action_text}했습니다!"
            await interaction.channel.send(notif)

            if not self.is_reservation and amount > 0:
                goals = SHIP_GOALS[self.stage]
                if all(data["progress"][self.stage].get(it, 0) >= qty for it, qty in goals.items()):
                    await interaction.channel.send(f"🎊 **{self.stage}단계 모든 재료 납품 완료!** 🎊")
                    idx = STAGE_ORDER.index(self.stage)
                    if idx < len(STAGE_ORDER) - 1:
                        next_s = STAGE_ORDER[idx + 1]
                        data["current_stage"] = next_s
                        save_data(data)
                        await interaction.channel.send(f"⚙️ 다음 단계인 **{next_s}단계**로 자동 전환되었습니다.")
        except ValueError:
            await interaction.response.send_message("❌ 숫자만 정확히 입력해주세요.", ephemeral=True)

# --- 버튼 뷰 ---
class DonationView(discord.ui.View):
    def __init__(self, stage, items, is_reservation=False):
        super().__init__(timeout=None)
        for item in items:
            self.add_item(DonationButton(item, stage, is_reservation))

class DonationButton(discord.ui.Button):
    def __init__(self, item_name, stage, is_reservation):
        label = f"{item_name} {'예약' if is_reservation else '제출'}"
        style = discord.ButtonStyle.success if is_reservation else discord.ButtonStyle.primary
        super().__init__(label=label, style=style)
        self.item_name = item_name
        self.stage = stage
        self.is_reservation = is_reservation

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DonationModal(self.item_name, self.stage, self.is_reservation))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

@bot.tree.command(name="현황", description="현재 단계 현황 확인 및 즉시 납품")
async def status(interaction: discord.Interaction):
    data = load_data()
    stage = data["current_stage"]
    goals = SHIP_GOALS[stage]
    progress = data["progress"].get(stage, {})
    
    embed = discord.Embed(title=f"🚢 현재 건조 현황 ({stage})", color=discord.Color.blue())
    for item, goal_qty in goals.items():
        done = progress.get(item, 0)
        pct = min(100, int((done / goal_qty) * 100))
        bar = "▰" * (pct // 10) + "▱" * (10 - (pct // 10))
        embed.add_field(name=f"{item} ({pct}%)", value=f"{bar}\n납품: {done}/{goal_qty} (남음: **{max(0, goal_qty-done)}**)", inline=False)
    
    await interaction.response.send_message(embed=embed, view=DonationView(stage, goals.keys(), False), ephemeral=True)

@bot.tree.command(name="미리보기", description="다른 단계의 예약 현황 확인 및 즉시 예약")
async def preview(interaction: discord.Interaction, stage: str):
    if stage in SHIP_GOALS:
        data = load_data()
        goals = SHIP_GOALS[stage]
        progress = data["progress"].get(stage, {})
        
        embed = discord.Embed(title=f"🔍 {stage}단계 예약 현황 미리보기", color=discord.Color.green())
        display_text = []
        for item, goal_qty in goals.items():
            done = progress.get(item, 0)
            left = max(0, goal_qty - done)
            display_text.append(f"• **{item}**: {done}/{goal_qty} (남은 예약: **{left}개**)")
        
        embed.description = "\n".join(display_text)
        embed.set_footer(text="아래 버튼을 눌러 바로 예약할 수 있습니다.")
        await interaction.response.send_message(embed=embed, view=DonationView(stage, goals.keys(), True), ephemeral=True)
    else:
        await interaction.response.send_message("❌ 올바른 단계(3-1~3-9)를 입력하세요.", ephemeral=True)

@bot.tree.command(name="단계변경", description="단계 수동 변경")
async def change_stage(interaction: discord.Interaction, stage: str):
    if stage in STAGE_ORDER:
        data = load_data()
        data["current_stage"] = stage
        save_data(data)
        await interaction.response.send_message(f"⚙️ 건조 단계가 **{stage}**로 변경되었습니다.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 단계 확인 필요", ephemeral=True)

@bot.tree.command(name="초기화", description="데이터 초기화")
async def reset(interaction: discord.Interaction):
    new_data = {"current_stage": "3-1", "progress": {k: {} for k in SHIP_GOALS.keys()}}
    save_data(new_data)
    await interaction.response.send_message("🚨 모든 데이터가 초기화되었습니다. (3-1단계 시작)")

# --- 실행부 ---
if __name__ == "__main__":
    keep_alive()  # Render가 봇을 끄지 못하게 Flask 서버를 먼저 켭니다.
    bot.run(TOKEN)