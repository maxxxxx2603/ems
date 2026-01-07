import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio

# --- CONFIGURATION ---
# Support à la fois config.json (local) et variables d'environnement (Railway)
if os.path.exists('config.json'):
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
else:
    config = {
        "TOKEN": os.environ.get("TOKEN"),
        "GUILD_ID": int(os.environ.get("GUILD_ID", 0)),
        "LOGS_CHANNEL_ID": int(os.environ.get("LOGS_CHANNEL_ID", 0)),
        "CV_CHANNEL_ID": int(os.environ.get("CV_CHANNEL_ID", 0)),
        "DEPOT_CV_CHANNEL_ID": int(os.environ.get("DEPOT_CV_CHANNEL_ID", 0)),
        "ROLE_ATTENTE_ID": int(os.environ.get("ROLE_ATTENTE_ID", 0)),
        "DISPO_CHANNEL_ID": int(os.environ.get("DISPO_CHANNEL_ID", 0)),
        "ROLE_DIRECTION_ID": int(os.environ.get("ROLE_DIRECTION_ID", 0))
    }

STATS_FILE = 'stats.json'

# Cooldown pour réactions
processed_reactions = set()

# --- COULEURS EMS ---
EMS_RED = discord.Color.from_rgb(220, 20, 60)
EMS_DARK_RED = discord.Color.from_rgb(178, 34, 52)

# --- SETUP BOT ---
class EMSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(CVButton())

bot = EMSBot()

# --- GESTION DES STATS ---
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            data = f.read().strip()
            if not data:
                return {}
            return json.loads(data)
    except:
        return {}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def extract_employee_name(channel_name):
    """Extrait le nom de l'employé du nom du channel"""
    if len(channel_name) > 1:
        return channel_name[1:].strip()
    return None

def get_color_emoji(count):
    """Retourne l'emoji couleur en fonction du nombre de réactions"""
    if count >= 100:
        return "🟢"
    elif count >= 50:
        return "🟠"
    else:
        return "🔴"

# --- SYSTEME DE RÉACTIONS ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.attachments or not message.channel.name:
        return
    
    # Éviter les traitements multiples
    if message.id in processed_reactions:
        return
    
    channel_name = message.channel.name
    
    # Vérifier si c'est un channel de réactions
    if len(channel_name) > 0 and channel_name[0] in ["🔴", "🟠", "🟢"]:
        processed_reactions.add(message.id)
        
        # Nettoyer si trop grand
        if len(processed_reactions) > 500:
            processed_reactions.clear()
        
        stats = load_stats()
        employee_name = extract_employee_name(channel_name)
        
        if not employee_name:
            return
        
        # Incrémenter le compteur
        if employee_name not in stats:
            stats[employee_name] = 0
        
        stats[employee_name] += 1
        current_count = stats[employee_name]
        save_stats(stats)
        
        # Ajouter réaction
        try:
            await message.add_reaction("✅")
        except:
            pass
        
        # Changer l'emoji du channel
        current_emoji = channel_name[0]
        new_emoji = get_color_emoji(current_count)
        
        if current_emoji != new_emoji:
            new_channel_name = f"{new_emoji}{channel_name[1:]}"
            try:
                await message.channel.edit(name=new_channel_name)
            except:
                pass
        
        # Envoyer log simplifié
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            new_emoji = get_color_emoji(current_count)
            
            # Message simple et normal
            message_text = f"✅ **{employee_name}** | {current_count} réas"
            
            try:
                await log_channel.send(message_text)
            except:
                pass

# --- COMMANDES ADMIN ---
@bot.tree.command(name="total", description="Affiche le total des réactions")
@app_commands.checks.has_permissions(administrator=True)
async def total(interaction: discord.Interaction):
    await interaction.response.defer()
    
    stats = load_stats()
    
    if not stats:
        embed = discord.Embed(
            title="🚑 Statistiques",
            description="Aucune donnée",
            color=EMS_RED
        )
        embed.set_footer(text="🚑 EMS System")
        await interaction.followup.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="🚑 📊 Statistiques",
        color=EMS_RED
    )
    
    for name, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        emoji = get_color_emoji(count)
        embed.add_field(name=f"{emoji} {name}", value=f"{count}/100", inline=False)
    
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="reset", description="Réinitialise les compteurs")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    save_stats({})
    
    embed = discord.Embed(
        title="🚑 ✅ Réinitialisation",
        description="Compteurs réinitialisés",
        color=EMS_RED
    )
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="semaine", description="Réinitialise la semaine - Remet tout à 0 et met en rouge")
@app_commands.checks.has_permissions(administrator=True)
async def semaine(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # Réinitialiser stats
    save_stats({})
    
    # Mettre tous les channels en 🔴 et garder la liste pour l'annonce
    announcement_channels = []
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            new_name = f"🔴{channel.name[1:]}"
            try:
                await channel.edit(name=new_name)
                announcement_channels.append(channel)
            except:
                pass
    
    # Embed d'annonce de semaine
    embed = discord.Embed(
        title="🚑 NOUVELLE SEMAINE !",
        description="**✅ Réinitialisation complète de la semaine**\n\n• Tous les compteurs remis à 0\n• Tous les channels en 🔴\n• C'est repartit de zéro !\n\n**Bonne chance à tous ! 💪**",
        color=EMS_RED
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571")
    embed.set_footer(text="🚑 EMS System | Nouvelle semaine, nouveau challenge !")

    # Envoyer l'annonce dans tous les channels avec emoji préfixe
    for channel in announcement_channels:
        try:
            await channel.send(embed=embed.copy())
        except:
            pass
    
    # Envoyer aussi dans le channel de logs
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel:
        try:
            await log_channel.send(embed=embed.copy())
        except:
            pass
    
    embed_confirm = discord.Embed(
        title="🚑 ✅ SEMAINE RÉINITIALISÉE",
        description="✅ Tous les compteurs remis à 0\n✅ Tous les channels changés en 🔴\n✅ Message posté en logs\n\nC'est parti pour une nouvelle semaine ! 🚀",
        color=EMS_RED
    )
    embed_confirm.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed_confirm)

# --- QUESTIONS DU CV ---
QUESTIONS = [
    "📄 **Candidature EMS**\nNom et Prénom ?",
    "🔹 **Informations personnelles**\nQuel est votre âge ?",
    "🚗 **Permis de conduire**\nAvez-vous le permis de conduire (si oui, le(s)quel(s) ?)",
    "⏳ **Présence en ville**\nDepuis quand êtes-vous en ville ?",
    "💼 **Expérience professionnelle**\nMétier actuelle ?",
    "📚 **Parcours**\nQuels métiers avez-vous déjà exercés ?",
    "🏥 **Compétences médicales**\nAvez-vous des compétences dans le domaine médical ?",
    "🔥 **Motivations**\nQuelles sont vos motivations à entrer chez les EMS ?",
    "⭐ **Pourquoi vous ?**\nPourquoi devrions-nous vous prendre et pas quelqu'un d'autre ?",
    "👍 **Qualités**\nDonnez-nous 3 qualités qui vous caractérisent",
    "⚠️ **Défauts**\nDonnez-nous 3 défauts qui vous caractérisent",
    "📅 **Disponibilités - Semaine**\nDu lundi au vendredi : [Horaire]",
    "📅 **Disponibilités - Week-end**\nWeek-end : [Horaire]"
]

# --- SYSTÈME DE CV ---
class ReviewView(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.message = None

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green, custom_id="accept_cv")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        role = guild.get_role(config.get("ROLE_ATTENTE_ID"))
        
        # Ajouter rôle
        if member and role:
            try:
                await member.add_roles(role)
            except:
                pass
        
        # DM
        try:
            await self.target_user.send(
                f"🎉 **FÉLICITATIONS !**\n\n"
                f"✅ Votre candidature a été **ACCEPTÉE** !\n\n"
                f"Bienvenue dans la famille des **EMS** ! 🚑\n\n"
                f"📝 **Prochaines étapes :**\n"
                f"1️⃣ Vérification de votre profil\n"
                f"2️⃣ Mise à jour de vos disponibilités\n"
                f"3️⃣ Onboarding\n\n"
                f"Nous vous recontacterons très prochainement pour les détails.\n\n"
                f"Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            embed = discord.Embed(
                title="✅ CV ACCEPTÉ",
                description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="✅ Statut", value="Candidature approuvée ✓", inline=False)
            embed.add_field(name="👤 Rôle attribué", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="🚑 EMS System")
            try:
                await log_channel.send(embed=embed)
            except:
                pass
        
        # Désactiver
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        await interaction.followup.send(f"✅ **{self.target_user.name}** a été accepté avec succès !", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # DM au candidat
        try:
            await self.target_user.send(
                f"❌ **Candidature Refusée**\n\n"
                f"Nous regrettons de vous informer que votre candidature n'a pas été retenue.\n\n"
                f"Nous vous encourageons à postuler à nouveau dans le futur.\n\n"
                f"Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            embed = discord.Embed(
                title="❌ CV REFUSÉ",
                description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_DARK_RED
            )
            embed.set_footer(text="🚑 EMS System")
            try:
                await log_channel.send(embed=embed)
            except:
                pass
        
        # Désactiver
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        await interaction.followup.send(f"✅ {self.target_user.mention} refusé", ephemeral=True)
    
    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

class CVButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Dépose ton CV", style=discord.ButtonStyle.primary, emoji="📝", custom_id="start_cv")
    async def start_cv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📋 Dossier en création...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # Vérifier si existe
        for ch in guild.text_channels:
            if ch.name == f"cv-{user_id}":
                await interaction.followup.send(f"❌ Dossier existe : {ch.mention}", ephemeral=True)
                return
        
        # Créer channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await guild.create_text_channel(
                f"cv-{user_id}",
                overwrites=overwrites,
                category=interaction.channel.category,
                topic=f"CV {interaction.user.name}"
            )
        except:
            await interaction.followup.send("❌ Erreur création", ephemeral=True)
            return
        
        await interaction.followup.send(f"📋 Channel créé : {channel.mention}", ephemeral=True)
        
        # Welcome
        welcome = discord.Embed(
            title="🚑 RECRUTEMENT EMS - FORMULAIRE DE CANDIDATURE",
            description=(
                f"Bienvenue **{interaction.user.mention}** ! 👋\n\n"
                f"Vous êtes sur le point de participer à notre processus de sélection pour l'équipe EMS.\n\n"
                f"**📋 Informations importantes :**\n"
                f"• {len(QUESTIONS)} questions à répondre\n"
                f"⏱️ 10 minutes par question\n"
                f"📝 Répondez de manière claire et détaillée\n"
                f"📸 Préparez vos documents (CV, diplômes, etc.)\n\n"
                f"**Bonne chance ! 💪**"
            ),
            color=EMS_RED
        )
        welcome.set_footer(text="🚑 EMS Management System | Let's go!")
        await channel.send(embed=welcome)
        await asyncio.sleep(2)
        
        # Questions
        answers = []
        user_fullname = None
        
        for i, question in enumerate(QUESTIONS, 1):
            q_embed = discord.Embed(
                title=f"❓ QUESTION {i}/{len(QUESTIONS)}",
                description=question,
                color=EMS_RED
            )
            q_embed.add_field(name="⏱️ Temps", value="Vous avez **10 minutes** pour répondre", inline=False)
            q_embed.set_footer(text="🚑 EMS System | Envoyez votre réponse ci-dessous")
            await channel.send(embed=q_embed)
            
            def check(m):
                return m.author == interaction.user and m.channel == channel
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=600)
                
                if i == 1:
                    user_fullname = msg.content
                    try:
                        member = guild.get_member(user_id)
                        if member:
                            await member.edit(nick=user_fullname)
                    except:
                        pass
                
                answers.append(f"**{question}**\n{msg.content}")
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="⏱️ TEMPS ÉCOULÉ",
                    description="Vous n'avez pas répondu à temps. Le dossier va être fermé.",
                    color=EMS_DARK_RED
                )
                timeout_msg.set_footer(text="🚑 EMS System")
                await channel.send(embed=timeout_msg)
                await asyncio.sleep(3)
                try:
                    await channel.delete()
                except:
                    pass
                return
        
        # Documents
        docs = discord.Embed(
            title="📎 DERNIÈRE ÉTAPE",
            description=(
                "Merci d'avoir complété le formulaire ! 🎉\n\n"
                "**Il ne manque plus que :**\n"
                "🆔 Votre carte d'identité\n"
                "🚗 Votre permis de conduire\n\n"
                "Envoyez-les ci-dessous et nous nous en chargerons ! 🚑\n\n"
                "⏱️ Vous avez un temps illimité pour envoyer les documents."
            ),
            color=EMS_RED
        )
        docs.set_footer(text="🚑 EMS System | Envoyez les fichiers ci-dessous")
        await channel.send(embed=docs)
        
        attachments = []
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        try:
            msg = await bot.wait_for('message', check=check_doc, timeout=None)
            
            if msg.attachments:
                for att in msg.attachments:
                    attachments.append(att.url)
            
            confirm = discord.Embed(
                title="✅ CANDIDATURE COMPLÈTE",
                description=(
                    "🎉 Excellent ! Nous avons reçu votre candidature complète !\n\n"
                    f"**Documents reçus :** {len(attachments)}\n\n"
                    "👀 **Prochaines étapes :**\n"
                    "• La direction examinera votre candidature\n"
                    "• Vous recevrez une réponse dans vos messages privés\n"
                    "• N'hésitez pas à nous contacter en cas de questions\n\n"
                    "**Merci pour votre intérêt envers les EMS !** 🚑"
                ),
                color=EMS_RED
            )
            confirm.set_footer(text="🚑 EMS System | Bon courage !")
            await channel.send(embed=confirm)
            
            try:
                await interaction.user.send("✅ Candidature reçue !")
            except:
                pass
        except:
            pass
        
        # Envoyer au channel CV
        cv_channel = bot.get_channel(config.get("CV_CHANNEL_ID"))
        if cv_channel:
            full_text = "\n\n".join(answers)
            cv_embed = discord.Embed(
                title=f"📋 CV - {user_fullname if user_fullname else interaction.user.name}",
                description=full_text[:2000],
                color=EMS_RED
            )
            
            if attachments:
                cv_embed.add_field(name="📎", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
            
            cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            cv_embed.set_footer(text=f"🚑 EMS System | ID: {user_id}")
            
            view = ReviewView(interaction.user)
            msg = await cv_channel.send(embed=cv_embed, view=view)
            view.message = msg
            
            # Ping direction
            direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
            if direction_role and config.get("ROLE_DIRECTION_ID") != 0:
                ping = discord.Embed(
                    title="📋 Nouveau CV",
                    description=f"{direction_role.mention}",
                    color=EMS_RED
                )
                ping.set_footer(text="🚑 EMS System")
                try:
                    await cv_channel.send(embed=ping)
                except:
                    pass
        
        # Nettoyer
        await asyncio.sleep(120)
        try:
            await channel.delete()
        except:
            pass

@bot.tree.command(name="setup_cv", description="Affiche le bouton CV")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cv(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚑 RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre équipe d'urgentistes !**\n\n"
            "Vous souhaitez intégrer une équipe dynamique et professionnelle ? "
            "Cliquez sur le bouton ci-dessous pour déposer votre candidature !\n\n"
            "**📋 Le processus :**\n"
            "1️⃣ Cliquez sur \"Dépose ton CV\"\n"
            "2️⃣ Répondez à 13 questions détaillées\n"
            "3️⃣ Envoyez vos documents\n"
            "4️⃣ Attendez la validation de la direction\n\n"
            "**✨ Nous cherchons :** Des candidats motivés, professionnels et passionnés par le secteur médical !\n\n"
            "**Bonne chance ! 🚑💪**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="🚑 EMS Management System | Votre avenir commence ici")
    await interaction.channel.send(embed=embed, view=CVButton())
    await interaction.response.send_message("✅ Message de recrutement posté !", ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ Bot: {bot.user}')
    stats = load_stats()
    print(f'📊 Stats: {stats if stats else "Aucune"}')

if __name__ == "__main__":
    try:
        bot.run(config['TOKEN'])
    except KeyboardInterrupt:
        print("Arrêt...")
    except Exception as e:
        print(f"Erreur: {e}")

