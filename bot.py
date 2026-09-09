"""
Bot Telegram per il Metodo Copertura Totale
Il bot assegna ambi univoci, gli utenti giocano autonomamente su Bari
"""

import os
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ========================
# CONFIGURAZIONE
# ========================

TOKEN = "8982225411:AAEka02r4LtnVVhfmwsayJehx4gxZ_Bw31E"
ADMIN_ID = 168250139

# Percorsi file
DATA_DIR = "data"
ASSIGNED_FILE = os.path.join(DATA_DIR, "ambi_assegnati.json")
USERS_FILE = os.path.join(DATA_DIR, "utenti.json")
STATS_FILE = os.path.join(DATA_DIR, "statistiche.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ========================
# LOGGING
# ========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========================
# GESTIONE DATI
# ========================

class DataManager:
    @staticmethod
    def load_json(file_path: str, default: any = None) -> any:
        if not os.path.exists(file_path):
            return default if default is not None else {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default if default is not None else {}
    
    @staticmethod
    def save_json(file_path: str, data: any) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def get_all_ambi() -> List[Tuple[int, int]]:
        return [(i, j) for i in range(1, 91) for j in range(i + 1, 91)]
    
    @staticmethod
    def ambo_to_str(ambo: Tuple[int, int]) -> str:
        return f"{ambo[0]:02d} - {ambo[1]:02d}"


class GameState:
    def __init__(self):
        self.users = DataManager.load_json(USERS_FILE, {})
        self.assigned = DataManager.load_json(ASSIGNED_FILE, {})
        self.stats = DataManager.load_json(STATS_FILE, {
            "total_users": 0,
            "total_assignments": 0,
            "daily_stats": {},
            "winners": [],
            "extraction_communicated": False,
            "extraction_date": None,
            "extraction_number": None,
            "ruota": "Bari"
        })
        self.config = DataManager.load_json(CONFIG_FILE, {
            "is_active": True,
            "max_users": 4005,
            "game_completed": False
        })
        self._update_available_cache()
    
    def _update_available_cache(self):
        all_ambi = set(DataManager.get_all_ambi())
        assigned_set = set(tuple(a) for a in self.assigned.values())
        self.available = list(all_ambi - assigned_set)
        self.available_count = len(self.available)
        
        if self.available_count == 0 and not self.stats.get("extraction_communicated", False):
            self.config["game_completed"] = True
            self.save_config()
    
    def assign_ambo(self, user_id: int, username: str = None) -> Optional[Tuple[int, int]]:
        if str(user_id) in self.assigned:
            return None
        if not self.available:
            return None
        if len(self.assigned) >= self.config.get("max_users", 4005):
            return None
        
        ambo = self.available.pop(0)
        self.assigned[str(user_id)] = list(ambo)
        
        if str(user_id) not in self.users:
            self.users[str(user_id)] = {
                "username": username or f"User_{user_id}",
                "joined_date": datetime.now().isoformat(),
                "ambo": list(ambo),
                "notifications": True,
                "extraction_played": False
            }
        else:
            self.users[str(user_id)]["ambo"] = list(ambo)
        
        self.available_count = len(self.available)
        self.stats["total_assignments"] += 1
        self.stats["total_users"] = len(self.assigned)
        
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.stats["daily_stats"]:
            self.stats["daily_stats"][today] = {"assignments": 0, "winners": 0}
        self.stats["daily_stats"][today]["assignments"] += 1
        
        if self.available_count == 0 and not self.stats.get("extraction_communicated", False):
            self.config["game_completed"] = True
            self.save_config()
        
        self.save_all()
        return ambo
    
    def get_user_ambo(self, user_id: int) -> Optional[Tuple[int, int]]:
        ambo = self.assigned.get(str(user_id))
        return tuple(ambo) if ambo else None
    
    def get_user_data(self, user_id: int) -> Optional[Dict]:
        return self.users.get(str(user_id))
    
    def set_extraction_date(self, date: str, number: str) -> None:
        self.stats["extraction_communicated"] = True
        self.stats["extraction_date"] = date
        self.stats["extraction_number"] = number
        self.config["game_completed"] = True
        self.save_all()
    
    def mark_extraction_played(self, user_id: int) -> None:
        if str(user_id) in self.users:
            self.users[str(user_id)]["extraction_played"] = True
            self.save_users()
    
    def get_statistics(self) -> Dict:
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "total_users": len(self.assigned),
            "max_users": self.config.get("max_users", 4005),
            "available": self.available_count,
            "total_assignments": self.stats["total_assignments"],
            "today_assignments": self.stats["daily_stats"].get(today, {}).get("assignments", 0),
            "is_active": self.config.get("is_active", True),
            "game_completed": self.config.get("game_completed", False),
            "extraction_communicated": self.stats.get("extraction_communicated", False),
            "extraction_date": self.stats.get("extraction_date"),
            "extraction_number": self.stats.get("extraction_number"),
            "ruota": self.stats.get("ruota", "Bari")
        }
    
    def reset_game(self) -> None:
        self.assigned = {}
        self.users = {}
        self.stats = {
            "total_users": 0,
            "total_assignments": 0,
            "daily_stats": {},
            "winners": [],
            "extraction_communicated": False,
            "extraction_date": None,
            "extraction_number": None,
            "ruota": "Bari"
        }
        self.config["is_active"] = True
        self.config["game_completed"] = False
        self._update_available_cache()
        self.save_all()
    
    def save_all(self) -> None:
        self.save_users()
        self.save_assigned()
        self.save_stats()
        self.save_config()
    
    def save_users(self) -> None:
        DataManager.save_json(USERS_FILE, self.users)
    
    def save_assigned(self) -> None:
        DataManager.save_json(ASSIGNED_FILE, self.assigned)
    
    def save_stats(self) -> None:
        DataManager.save_json(STATS_FILE, self.stats)
    
    def save_config(self) -> None:
        DataManager.save_json(CONFIG_FILE, self.config)


class LottoBot:
    def __init__(self, token: str):
        self.token = token
        self.state = GameState()
        self.application = None
    
    def run(self):
        self.application = Application.builder().token(self.token).build()
        
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("mioambo", self.cmd_mio_ambo))
        self.application.add_handler(CommandHandler("statistiche", self.cmd_statistiche))
        self.application.add_handler(CommandHandler("estrazionedagiocare", self.cmd_estrazione_da_giocare))
        self.application.add_handler(CommandHandler("classifica", self.cmd_classifica))
        
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))
        self.application.add_handler(CommandHandler("comunicaestrazione", self.cmd_comunica_estrazione))
        self.application.add_handler(CommandHandler("reset", self.cmd_reset))
        self.application.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        self.application.add_handler(CommandHandler("esporta", self.cmd_esporta))
        self.application.add_handler(CommandHandler("verificaestrazione", self.cmd_verifica_estrazione))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("Bot avviato!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        existing_ambo = self.state.get_user_ambo(user_id)
        
        if existing_ambo:
            stats = self.state.get_statistics()
            message = (
                f"👋 Bentornato {username}!\n\n"
                f"🎯 **Il tuo ambo:** {DataManager.ambo_to_str(existing_ambo)}\n"
                f"🎲 **Ruota:** {stats['ruota']}\n"
                f"📊 Ambi rimasti: {self.state.available_count}/4005\n"
            )
            
            if stats.get("extraction_communicated"):
                message += (
                    f"\n📢 **ESTRAZIONE COMUNICATA!**\n"
                    f"📅 Data: {stats['extraction_date']}\n"
                    f"🔢 Estrazione: {stats['extraction_number']}\n"
                    f"\n⚠️ **Ricorda:** Devi giocare il tuo ambo sulla ruota di {stats['ruota']}!\n"
                    f"Usa /estrazionedagiocare per rivedere i dettagli."
                )
            else:
                message += (
                    f"\n⏳ In attesa che tutti i 4005 ambi siano assegnati.\n"
                    f"📢 Quando sarà completato, riceverai la data dell'estrazione.\n\n"
                    f"💡 **Invita altre persone** per completare il sistema più velocemente!"
                )
            
            await update.message.reply_text(message, parse_mode="Markdown")
            return
        
        if not self.state.config.get("is_active", True):
            await update.message.reply_text(
                "⛔ Il sistema è attualmente in pausa.\n"
                "Attendi la prossima partita per partecipare."
            )
            return
        
        if self.state.available_count == 0:
            await update.message.reply_text(
                "❌ Tutti i 4005 ambi sono già stati assegnati!\n"
                "Attendi la comunicazione dell'estrazione."
            )
            return
        
        ambo = self.state.assign_ambo(user_id, username)
        
        if ambo:
            keyboard = [
                [InlineKeyboardButton("📊 Vedi Statistiche", callback_data="stats")],
                [
                    InlineKeyboardButton("🔔 Attiva Notifiche", callback_data="notify_on"),
                    InlineKeyboardButton("🔕 Disattiva Notifiche", callback_data="notify_off")
                ],
                [InlineKeyboardButton("ℹ️ Come funziona", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            stats = self.state.get_statistics()
            
            await update.message.reply_text(
                f"🎯 **BENVENUTO NEL SISTEMA!** 🎯\n\n"
                f"Hai appena ricevuto un ambo unico che **nessun altro giocherà**.\n\n"
                f"📌 **Il tuo ambo:** {DataManager.ambo_to_str(ambo)}\n"
                f"🎲 **Ruota:** {stats['ruota']}\n\n"
                f"---\n\n"
                f"⚡ **COME FUNZIONA:**\n\n"
                f"1️⃣ **Non giochiamo noi per te** – Dovrai recarti personalmente al ricevitore e giocare il tuo ambo sulla ruota di Bari.\n\n"
                f"2️⃣ **Stiamo distribuendo 4.005 ambi diversi** a 4.005 persone. Ogni persona riceve un ambo differente, senza duplicati.\n\n"
                f"3️⃣ Quando tutti i 4.005 ambi saranno distribuiti, **il sistema sarà completo**.\n\n"
                f"4️⃣ A quel punto, ti comunicheremo la **data e il numero dell'estrazione** su cui giocare.\n\n"
                f"5️⃣ Dovrai giocare il tuo ambo **esattamente su quell'estrazione**.\n\n"
                f"---\n\n"
                f"💰 **LA CERTEZZA:**\n\n"
                f"Quando i 4.005 ambi saranno tutti giocati sulla stessa estrazione, **avremo la certezza assoluta che ci saranno dei vincitori**.\n\n"
                f"Il sistema è progettato in modo che, su quell'estrazione, **10 persone vinceranno 250€ ciascuna** (con 1€ di giocata).\n\n"
                f"---\n\n"
                f"📌 **COSA DEVI FARE ORA:**\n\n"
                f"1. Conserva il tuo ambo: **{DataManager.ambo_to_str(ambo)}**\n"
                f"2. Invita altre persone a partecipare – più siamo, più velocemente si completa il sistema\n"
                f"3. Aspetta la comunicazione dell'estrazione\n"
                f"4. Vai al ricevitore e gioca il tuo ambo sulla ruota di Bari all'estrazione indicata\n\n"
                f"---\n\n"
                f"📊 **Ambi rimasti:** {self.state.available_count}/4005\n\n"
                f"💡 **Invita amici e conoscenti** per completare il sistema più velocemente!",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            
            if self.state.available_count == 0 and not self.state.stats.get("extraction_communicated", False):
                await self.notify_all(
                    f"🎉 **SISTEMA COMPLETATO!** 🎉\n\n"
                    f"Tutti i 4.005 ambi sono stati distribuiti!\n\n"
                    f"📢 **A breve riceverai la comunicazione con:**\n"
                    f"• La data dell'estrazione\n"
                    f"• Il numero dell'estrazione\n"
                    f"• Le istruzioni per giocare\n\n"
                    f"---\n\n"
                    f"💰 **RICORDA:**\n\n"
                    f"Su questa estrazione, **10 persone vinceranno 250€** (con 1€ di giocata).\n\n"
                    f"Il sistema è stato progettato per garantire questo risultato.\n\n"
                    f"🎯 **1€ di giocata → 250€ di vincita per 10 persone!**\n\n"
                    f"---\n\n"
                    f"⏳ **Attendi la comunicazione dell'amministratore.**"
                )
        else:
            await update.message.reply_text(
                "❌ Si è verificato un errore nell'assegnazione.\n"
                "Riprova più tardi o contatta l'amministratore."
            )
    
    async def cmd_mio_ambo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        ambo = self.state.get_user_ambo(user_id)
        
        if not ambo:
            await update.message.reply_text(
                "❌ Non hai ancora un ambo assegnato.\n"
                "Usa /start per ottenerne uno."
            )
            return
        
        stats = self.state.get_statistics()
        
        message = (
            f"🎯 **Il tuo Ambo**\n\n"
            f"📌 **Numero:** {DataManager.ambo_to_str(ambo)}\n"
            f"🎲 **Ruota:** {stats['ruota']}\n"
            f"👥 **Utenti totali:** {len(self.state.assigned)}/4005\n"
            f"📦 **Ambi disponibili:** {self.state.available_count}\n"
        )
        
        if stats.get("extraction_communicated"):
            message += (
                f"\n📢 **Estrazione comunicata:**\n"
                f"📅 Data: {stats['extraction_date']}\n"
                f"🔢 Estrazione: {stats['extraction_number']}\n"
                f"\n⚠️ Ricorda di giocare il tuo ambo sulla ruota di {stats['ruota']}!"
            )
        else:
            message += (
                f"\n⏳ In attesa della comunicazione dell'estrazione."
            )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    async def cmd_estrazione_da_giocare(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        ambo = self.state.get_user_ambo(user_id)
        
        if not ambo:
            await update.message.reply_text(
                "❌ Non hai un ambo assegnato. Usa /start per partecipare."
            )
            return
        
        stats = self.state.get_statistics()
        
        if not stats.get("extraction_communicated"):
            await update.message.reply_text(
                "⏳ L'estrazione non è ancora stata comunicata.\n"
                "Attendi che tutti i 4005 ambi siano assegnati.\n\n"
                f"📊 Ambi rimasti: {self.state.available_count}/4005"
            )
            return
        
        await update.message.reply_text(
            f"🎯 **LA TUA GIOCATA**\n\n"
            f"📌 **Ambo:** {DataManager.ambo_to_str(ambo)}\n"
            f"🎲 **Ruota:** {stats['ruota']}\n"
            f"📅 **Data:** {stats['extraction_date']}\n"
            f"🔢 **Estrazione:** {stats['extraction_number']}\n\n"
            f"---\n\n"
            f"⚠️ **RICORDA:**\n"
            f"• Vai al ricevitore del Lotto\n"
            f"• Gioca l'ambo **{DataManager.ambo_to_str(ambo)}**\n"
            f"• Sulla ruota di **{stats['ruota']}**\n"
            f"• All'estrazione del **{stats['extraction_date']}**\n\n"
            f"---\n\n"
            f"💰 **LA CERTEZZA:**\n\n"
            f"Su questa estrazione, **10 persone vinceranno 250€** (con 1€ di giocata).\n\n"
            f"Il sistema è stato progettato per garantire che su questa estrazione ci siano dei vincitori. **Uno di noi sarà tra questi!**\n\n"
            f"🎯 **In bocca al lupo!**",
            parse_mode="Markdown"
        )
    
    async def cmd_statistiche(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        stats = self.state.get_statistics()
        coverage = (stats["total_users"] / stats["max_users"]) * 100 if stats["max_users"] > 0 else 0
        
        message = (
            f"📊 **Statistiche Sistema**\n\n"
            f"👥 **Utenti:** {stats['total_users']}/{stats['max_users']} ({coverage:.1f}%)\n"
            f"📦 **Ambi disponibili:** {stats['available']}\n"
            f"📝 **Assegnazioni totali:** {stats['total_assignments']}\n"
            f"📅 **Assegnazioni oggi:** {stats['today_assignments']}\n"
            f"🎲 **Ruota:** {stats['ruota']}\n"
            f"📌 **Stato:** "
        )
        
        if stats.get("extraction_communicated"):
            message += f"📢 Estrazione comunicata!\n"
            message += f"📅 Data: {stats['extraction_date']}\n"
            message += f"🔢 Estrazione: {stats['extraction_number']}"
        elif stats['available'] == 0:
            message += "⏳ Attesa comunicazione estrazione..."
        else:
            message += f"🟢 In attesa di {stats['available']} giocatori"
        
        keyboard = [[InlineKeyboardButton("🔄 Aggiorna", callback_data="refresh_stats")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    
    async def cmd_classifica(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        winners = self.state.stats.get("winners", [])
        
        if not winners:
            await update.message.reply_text(
                "📊 Nessun vincitore registrato.\n"
                "Attendi l'estrazione!"
            )
            return
        
        message = "🏆 **Vincitori** 🏆\n\n"
        for i, winner in enumerate(winners[:10], 1):
            ambo_str = DataManager.ambo_to_str(tuple(winner["ambo"]))
            message += f"{i}. {winner['username']} - {ambo_str}\n"
        
        if len(winners) > 10:
            message += f"\n... e altri {len(winners) - 10} vincitori."
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = (
            "📖 **COME FUNZIONA IL SISTEMA**\n\n"
            "🎯 **Il concetto:**\n\n"
            "Stiamo distribuendo 4.005 ambi diversi a 4.005 persone. Ogni persona riceve un ambo unico, senza duplicati.\n\n"
            "Quando tutti i 4.005 ambi saranno distribuiti, giocheremo tutti sulla stessa estrazione.\n\n"
            "💰 **La certezza:**\n\n"
            "Il sistema è progettato per garantire che su quell'estrazione ci siano dei vincitori.\n\n"
            "**10 persone vinceranno 250€ ciascuna** (con 1€ di giocata).\n\n"
            "---\n\n"
            "📌 **I TUOI COMPITI:**\n\n"
            "1. Ricevi il tuo ambo con /start\n"
            "2. Invita altre persone a partecipare\n"
            "3. Quando riceverai la comunicazione, gioca il tuo ambo alla data indicata\n"
            "4. Incrocia le dita!\n\n"
            "---\n\n"
            "**Comandi disponibili:**\n"
            "/start - Ricevi il tuo ambo\n"
            "/mioambo - Mostra il tuo ambo\n"
            "/estrazionedagiocare - Mostra i dati della giocata\n"
            "/statistiche - Statistiche del sistema\n"
            "/classifica - Vincitori\n"
            "/help - Questa guida"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato. Solo amministratori.")
            return
        
        stats = self.state.get_statistics()
        
        keyboard = [
            [InlineKeyboardButton("📊 Statistiche Dettagliate", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Comunica Estrazione", callback_data="admin_estrazione")],
            [InlineKeyboardButton("📢 Broadcast Messaggio", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔄 Reset Sistema", callback_data="admin_reset")],
            [InlineKeyboardButton("📦 Esporta Dati", callback_data="admin_export")],
            [InlineKeyboardButton("⏸️ Pausa/Riprendi", callback_data="admin_toggle")],
            [InlineKeyboardButton("✅ Verifica Estrazione", callback_data="admin_verifica")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status = "🟢 Attivo"
        if stats.get("extraction_communicated"):
            status = "📢 Estrazione Comunicata"
        elif stats['available'] == 0:
            status = "⏳ Completo - Attesa Comunicazione"
        
        await update.message.reply_text(
            f"🔐 **Pannello Amministratore**\n\n"
            f"👥 Utenti: {stats['total_users']}/{stats['max_users']}\n"
            f"📦 Ambi disponibili: {stats['available']}\n"
            f"📌 Stato: {status}\n"
            f"🎲 Ruota: {stats['ruota']}\n\n"
            f"Seleziona un'azione:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    async def cmd_comunica_estrazione(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato.")
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "📝 **Formato:**\n"
                "/comunicaestrazione [data] [numero_estrazione]\n\n"
                "Esempio: /comunicaestrazione 10/09/2026 1°\n"
                "Esempio: /comunicaestrazione 15/09/2026 2°"
            )
            return
        
        date = args[0]
        number = " ".join(args[1:])
        
        self.state.set_extraction_date(date, number)
        
        stats = self.state.get_statistics()
        await self.notify_all(
            f"📢 **ESTRAZIONE COMUNICATA!** 📢\n\n"
            f"Il sistema è completo! Tutti i 4.005 ambi sono stati distribuiti.\n\n"
            f"🎯 **I TUOI DATI DI GIOCO:**\n"
            f"• Ambo: consulta il tuo ambo con /mioambo\n"
            f"• Ruota: {stats['ruota']}\n"
            f"• Data estrazione: {date}\n"
            f"• Estrazione: {number}\n\n"
            f"---\n\n"
            f"⚠️ **ISTRUZIONI:**\n\n"
            f"1. Vai al ricevitore del Lotto\n"
            f"2. Gioca il tuo ambo\n"
            f"3. Sulla ruota di **{stats['ruota']}**\n"
            f"4. All'estrazione del **{date}**\n\n"
            f"---\n\n"
            f"💰 **RICORDA:**\n\n"
            f"Su questa estrazione, **10 persone vinceranno 250€** (con 1€ di giocata).\n\n"
            f"Il sistema è stato progettato per garantire questo risultato. **Uno di noi vincerà sicuramente!**\n\n"
            f"---\n\n"
            f"📌 Usa /estrazionedagiocare per rivedere i tuoi dati in qualsiasi momento.\n\n"
            f"🎯 **Buona fortuna a tutti!**"
        )
        
        await update.message.reply_text(
            f"✅ **Estrazione comunicata!**\n\n"
            f"📅 Data: {date}\n"
            f"🔢 Estrazione: {number}\n"
            f"🎲 Ruota: {stats['ruota']}\n"
            f"📢 Notifica inviata a {len(self.state.users)} utenti."
        )
    
    async def cmd_verifica_estrazione(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato.")
            return
        
        args = context.args
        if len(args) != 5:
            await update.message.reply_text(
                "📝 **Formato:**\n"
                "/verificaestrazione n1 n2 n3 n4 n5\n\n"
                "Esempio: /verificaestrazione 5 12 23 45 67\n\n"
                "Inserisci i 5 numeri estratti per trovare i vincitori."
            )
            return
        
        try:
            numbers = [int(n) for n in args]
            if not all(1 <= n <= 90 for n in numbers):
                raise ValueError("I numeri devono essere tra 1 e 90")
            if len(set(numbers)) != 5:
                raise ValueError("I numeri devono essere tutti diversi")
        except ValueError as e:
            await update.message.reply_text(f"❌ Errore: {str(e)}")
            return
        
        winners = []
        winning_ambi = []
        
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                winning_ambi.append(sorted([numbers[i], numbers[j]]))
        
        for user_id, ambo in self.state.assigned.items():
            if sorted(ambo) in winning_ambi:
                user_data = self.state.users.get(user_id, {})
                winners.append({
                    "user_id": user_id,
                    "username": user_data.get("username", "Anonimo"),
                    "ambo": ambo,
                    "timestamp": datetime.now().isoformat()
                })
        
        self.state.stats["winners"] = winners
        self.state.save_stats()
        
        if winners:
            message = "🎉 **VINCITORI TROVATI!** 🎉\n\n"
            message += f"📅 Numeri estratti: {', '.join(map(str, numbers))}\n\n"
            for i, w in enumerate(winners, 1):
                ambo_str = DataManager.ambo_to_str(tuple(w["ambo"]))
                message += f"{i}. {w['username']} - {ambo_str}\n"
            
            for winner in winners:
                try:
                    ambo_str = DataManager.ambo_to_str(tuple(winner["ambo"]))
                    await self.application.bot.send_message(
                        chat_id=int(winner["user_id"]),
                        text=(
                            f"🎉 **CONGRATULAZIONI! HAI VINTO!** 🎉\n\n"
                            f"Ambo: **{ambo_str}**\n"
                            f"Ruota: Bari\n"
                            f"Numeri estratti: {', '.join(map(str, numbers))}\n\n"
                            f"💰 Hai vinto **250€**!\n"
                            f"Contatta l'amministratore per ricevere il premio."
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Errore notifica vincitore {winner['user_id']}: {e}")
            
            await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"❌ Nessun vincitore trovato.\n\n"
                f"Numeri estratti: {', '.join(map(str, numbers))}\n"
                f"Riprova a verificare i numeri."
            )
    
    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato.")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Sì, resetta tutto", callback_data="confirm_reset"),
                InlineKeyboardButton("❌ Annulla", callback_data="cancel_reset")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **ATTENZIONE: Reset del Sistema**\n\n"
            "Questa operazione cancellerà:\n"
            "- Tutti gli utenti e i loro ambi\n"
            "- Tutte le statistiche\n"
            "- I vincitori registrati\n"
            "- La comunicazione dell'estrazione\n\n"
            "**Sei sicuro di voler continuare?**",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    async def cmd_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato.")
            return
        
        message = " ".join(context.args)
        if not message:
            await update.message.reply_text(
                "📝 **Formato:** /broadcast [messaggio]\n\n"
                "Esempio: /broadcast Nuova estrazione stasera!"
            )
            return
        
        sent_count = await self.notify_all(message)
        
        await update.message.reply_text(
            f"✅ Messaggio inviato a {sent_count} utenti."
        )
    
    async def cmd_esporta(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ Accesso negato.")
            return
        
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["User ID", "Username", "Ambo", "Data", "Ha Giocato", "Notifiche"])
        
        for user_id, data in self.state.users.items():
            ambo = self.state.get_user_ambo(int(user_id))
            writer.writerow([
                user_id,
                data.get("username", ""),
                DataManager.ambo_to_str(ambo) if ambo else "",
                data.get("joined_date", ""),
                "Sì" if data.get("extraction_played", False) else "No",
                "Sì" if data.get("notifications", True) else "No"
            ])
        
        output.seek(0)
        
        await update.message.reply_document(
            document=output.getvalue().encode('utf-8'),
            filename=f"dati_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            caption="📊 Dati esportati del sistema"
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "stats" or data == "refresh_stats":
            stats = self.state.get_statistics()
            coverage = (stats["total_users"] / stats["max_users"]) * 100 if stats["max_users"] > 0 else 0
            
            message = (
                f"📊 **Statistiche Sistema**\n\n"
                f"👥 **Utenti:** {stats['total_users']}/{stats['max_users']} ({coverage:.1f}%)\n"
                f"📦 **Ambi disponibili:** {stats['available']}\n"
                f"📝 **Assegnazioni totali:** {stats['total_assignments']}\n"
                f"📅 **Assegnazioni oggi:** {stats['today_assignments']}\n"
                f"🎲 **Ruota:** {stats['ruota']}\n"
            )
            
            if stats.get("extraction_communicated"):
                message += f"📢 Estrazione: {stats['extraction_date']} - {stats['extraction_number']}"
            elif stats['available'] == 0:
                message += "⏳ Attesa comunicazione estrazione..."
            else:
                message += f"🟢 In attesa di {stats['available']} giocatori"
            
            await query.edit_message_text(message, parse_mode="Markdown")
        
        elif data == "notify_on":
            if str(user_id) in self.state.users:
                self.state.users[str(user_id)]["notifications"] = True
                self.state.save_users()
                await query.edit_message_text("🔔 Notifiche attivate! Riceverai aggiornamenti.")
            else:
                await query.edit_message_text("⚠️ Usa /start prima di attivare le notifiche.")
        
        elif data == "notify_off":
            if str(user_id) in self.state.users:
                self.state.users[str(user_id)]["notifications"] = False
                self.state.save_users()
                await query.edit_message_text("🔕 Notifiche disattivate.")
            else:
                await query.edit_message_text("⚠️ Usa /start prima di disattivare le notifiche.")
        
        elif data == "help":
            help_text = (
                "📖 **COME FUNZIONA:**\n\n"
                "1. /start per ricevere il tuo ambo\n"
                "2. **Gioca tu personalmente** l'ambo sulla ruota Bari\n"
                "3. Quando tutti gli ambi sono assegnati, riceverai la data dell'estrazione\n"
                "4. Gioca il tuo ambo all'estrazione indicata\n"
                "5. **10 persone vinceranno 250€**\n\n"
                "📌 **Comandi:** /mioambo, /estrazionedagiocare, /statistiche, /classifica"
            )
            await query.edit_message_text(help_text, parse_mode="Markdown")
        
        elif data.startswith("admin_"):
            if user_id != ADMIN_ID:
                await query.edit_message_text("⛔ Accesso negato.")
                return
            
            if data == "admin_stats":
                stats = self.state.get_statistics()
                message = (
                    f"📊 **Statistiche Dettagliate**\n\n"
                    f"👥 Utenti: {stats['total_users']}/{stats['max_users']}\n"
                    f"📦 Ambi disponibili: {stats['available']}\n"
                    f"📝 Assegnazioni: {stats['total_assignments']}\n"
                    f"🎲 Ruota: {stats['ruota']}\n"
                    f"📌 Stato: {'Completato' if stats['game_completed'] else 'In corso'}\n"
                    f"📢 Estrazione comunicata: {'Sì' if stats['extraction_communicated'] else 'No'}\n"
                    f"📅 Data estrazione: {stats.get('extraction_date', 'N/A')}\n"
                    f"🔢 Estrazione: {stats.get('extraction_number', 'N/A')}"
                )
                await query.edit_message_text(message, parse_mode="Markdown")
            
            elif data == "admin_estrazione":
                await query.edit_message_text(
                    "📢 **Comunica Estrazione**\n\n"
                    "Usa il comando:\n"
                    "`/comunicaestrazione [data] [numero_estrazione]`\n\n"
                    "Esempio: `/comunicaestrazione 10/09/2026 1°`\n\n"
                    "⚠️ Questo comando notificherà TUTTI gli utenti."
                )
            
            elif data == "admin_broadcast":
                await query.edit_message_text(
                    "📢 **Broadcast Messaggio**\n\n"
                    "Usa il comando:\n"
                    "`/broadcast [messaggio]`\n\n"
                    "Esempio: `/broadcast Nuova estrazione stasera!`"
                )
            
            elif data == "admin_reset":
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Sì, resetta", callback_data="confirm_reset"),
                        InlineKeyboardButton("❌ Annulla", callback_data="cancel_reset")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚠️ **RESET COMPLETO**\n\n"
                    "Questa azione è irreversibile!\n"
                    "Cancellerà tutti i dati.\n\n"
                    "Sei sicuro?",
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            
            elif data == "admin_export":
                import io
                import csv
                
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["User ID", "Username", "Ambo", "Data", "Ha Giocato", "Notifiche"])
                
                for user_id, user_data in self.state.users.items():
                    ambo = self.state.get_user_ambo(int(user_id))
                    writer.writerow([
                        user_id,
                        user_data.get("username", ""),
                        DataManager.ambo_to_str(ambo) if ambo else "",
                        user_data.get("joined_date", ""),
                        "Sì" if user_data.get("extraction_played", False) else "No",
                        "Sì" if user_data.get("notifications", True) else "No"
                    ])
                
                output.seek(0)
                
                await query.message.reply_document(
                    document=output.getvalue().encode('utf-8'),
                    filename=f"dati_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    caption="📊 Dati esportati"
                )
                await query.edit_message_text("✅ Dati esportati!")
            
            elif data == "admin_toggle":
                current_state = self.state.config.get("is_active", True)
                self.state.config["is_active"] = not current_state
                self.state.save_config()
                
                new_state = "🟢 ATTIVO" if self.state.config["is_active"] else "🔴 IN PAUSA"
                await query.edit_message_text(
                    f"✅ Stato aggiornato: **{new_state}**"
                )
            
            elif data == "admin_verifica":
                await query.edit_message_text(
                    "✅ **Verifica Estrazione**\n\n"
                    "Usa il comando:\n"
                    "`/verificaestrazione n1 n2 n3 n4 n5`\n\n"
                    "Esempio: `/verificaestrazione 5 12 23 45 67`\n\n"
                    "Inserisci i 5 numeri estratti per trovare i vincitori."
                )
        
        elif data == "confirm_reset":
            if user_id == ADMIN_ID:
                self.state.reset_game()
                await query.edit_message_text(
                    "✅ **Reset completato!**\n\n"
                    "Tutti i dati sono stati cancellati.\n"
                    "Il sistema è pronto per un nuovo ciclo."
                )
        
        elif data == "cancel_reset":
            await query.edit_message_text("✅ Reset annullato.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text
        
        if text.lower() in ["ciao", "salve", "hello"]:
            await update.message.reply_text(
                "👋 Ciao! Usa /start per ricevere il tuo ambo."
            )
        elif "ambo" in text.lower():
            await update.message.reply_text(
                "🎯 Usa /start per ottenere il tuo ambo!\n"
                "Usa /mioambo per rivederlo."
            )
        elif "estrazione" in text.lower():
            await update.message.reply_text(
                "🎯 Usa /estrazionedagiocare per vedere l'estrazione da giocare."
            )
        else:
            await update.message.reply_text(
                "❓ Non ho capito. Usa /help per vedere i comandi disponibili."
            )
    
    async def notify_all(self, message: str) -> int:
        sent_count = 0
        for user_id in self.state.users:
            try:
                await self.application.bot.send_message(
                    chat_id=int(user_id),
                    text=message,
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Errore invio messaggio a {user_id}: {e}")
        return sent_count


def main():
    try:
        bot = LottoBot(TOKEN)
        bot.run()
    except Exception as e:
        logger.error(f"Errore fatale: {e}")
        raise


if __name__ == "__main__":
    main()