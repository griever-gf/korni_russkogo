import re
import pymorphy2
import mysql.connector
import os
import sys
import random
import urllib.parse as urlparse
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from telegram import ChatMember

try:
    import config
except ModuleNotFoundError:
    # if no config (i.e. prod)
    pass

PORT = int(os.environ.get('PORT', 3306))
morph = pymorphy2.MorphAnalyzer()


def message_how(update, context):
    # Send a message when the command /kak is issued.
    update.message.reply_text('Способы использования:\nНаилучший способ - добавить (ро)бота к себе в болталки (беседы),'
                            ' тогда он будет поправлять всех участников. Для "супергрупп" необходимы права заведующего.'
                            '\n\nУпрощённый способ - просто присылать любые письмена боту в личку, он тоже будет'
                            ' их поправлять. Но придётся каждый раз вручную это делать.')


def message_info(update, context):
    # Send a message when the command /sved is issued.
    update.message.reply_text('Дополнительные сведения можно изведать по ссылке:\n'
                            'https://telegra.ph/Robot-popravlyalshchik-dlya-Telegrama-Korni-russkogo-04-10')


def connect_to_db():
    try:
        if 'CLEARDB_DATABASE_URL' in os.environ:  # if prod
            url = urlparse.urlparse(os.environ['CLEARDB_DATABASE_URL'])
            connect = mysql.connector.connect(database=url.path[1:], user=url.username, password=url.password,
                                              host=url.hostname, port=url.port)
        else:
            connect = mysql.connector.connect(database=config.db_name, user=config.db_user, password=config.db_password,
                                              host=config.db_host)
    except mysql.connector.Error as e:
        print('Unable to connect!\n{0}').format(e)
        connect = None
    finally:
        return connect


def get_db_frequency(cht_id):
    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor()
    else:
        sys.exit(1)
    cursor.execute("SELECT freq FROM freq_data WHERE chat_id='" + str(cht_id) + "'")
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if res is not None:
        return res[0]
    else:
        print("Can't extract frequency for chat " + str(cht_id))
        return res


def change_react_frequency(update, context):
    def send_message_when_wrong_argument():
        update.message.reply_text("Используйте целое числовое значение в промежутке от 1 до 50 в строке после приказа "
                                  "/vzvod и пробела для настройки ретивости робота в данной болталке.\nНапример: "
                                  "\"/vzvod 1\" - взводиться всегда, \"/vzvod 2\" - взводиться на каждое второе "
                                  "сообщение, \"/vzvod 10\" - взводиться на каждое десятое и т.п.")
    # Process when the command /vzvod is issued.
    if update.message is None:
        return
    if update.message.chat.type == "private":
        update.message.reply_text("Настройка ретивости робота доступна только при использовании в болталках,"
                                  " а не в личке!")
        return
    else:
        if context.bot.getChatMember(update.effective_chat.id, update.effective_user.id).status not in \
                                    [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]:
            update.message.reply_text("Настройка ретивости робота доступна лишь пользователям с правами заведующего!")
            return
    if len(context.args) > 0:
        try:
            param = int(context.args[0])
        except ValueError:
            send_message_when_wrong_argument()
            return
    else:
        send_message_when_wrong_argument()
        return
    if (param < 1) | (param > 50):
        send_message_when_wrong_argument()
        return
    set_db_frequency(param, update)
    update.message.reply_text("Ретивость робота в данной болталке установлена на " +
                              f'{100/param:4.2f}'.replace('.', ',') + "%")


def set_db_frequency(fq, update):
    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor()
    else:
        sys.exit(1)

    id_chat_id = "chat_id"
    id_chat_caption = "chat_caption"
    id_chat_username = "username"
    id_freq = "freq"

    chat_id = update.effective_chat.id
    title = update.effective_chat.title
    if title is None:
        title = "PRIVATE" if (update.message.chat.type == "private") else "NONE"

    username = update.effective_chat.username
    if username is None:
        if update.message.chat.type == "private":
            user_username = update.effective_user.username
            username = "@" + user_username if (user_username is not None) else update.effective_user.first_name
        else:
            username = "NONE"

    cursor.execute(
        "INSERT INTO freq_data(" + id_chat_id + "," + id_chat_caption + "," + id_chat_username + "," + id_freq +
        ") VALUES(" + str(chat_id) + ", '" + title + "', '" + username + "', " + str(fq) + ") " +
        "ON DUPLICATE KEY UPDATE " +
        id_chat_caption + "='" + title + "', " + id_chat_username + "='" + username + "', " + id_freq + "=" + str(fq))

    conn.commit()
    cursor.close()
    conn.close()


# Let's analyze all the incoming text
def process_text(update, context):
    if update.message is None:
        return

    chat_id = update.effective_chat.id

    current_freq = get_db_frequency(chat_id)
    if current_freq is None:
        current_freq = 1
        set_db_frequency(current_freq, update)

    is_no_message_process = (random.randint(1, current_freq) != 1)
    if is_no_message_process & (update.message.chat.type != "private"):
        return

    text_to_split = update.message.caption if (update.message.text is None) else update.message.text

    # checks before processing
    if update.message.chat.type != "private":
        bot_chat_member = context.bot.getChatMember(update.effective_chat.id, context.bot.id)
        if bot_chat_member.status == ChatMember.RESTRICTED:
            if not bot_chat_member.can_send_messages:
                return
    else:
        if text_to_split == "/start":
            message_how(update, context)
            return

    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor()
    else:
        sys.exit(1)

    id_non_native = "МУСОРНОЕ"
    id_native = "РОДНОЕ"
    id_exclusions = "ИСКЛЮЧЁННЫЕ ИСКАЖЕНИЯ"
    id_inexact = "ПОПРАВКА НА СЛУЧАЙ НЕМУСОРНОГО"

    output_message = ""

    # let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    # [\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w-]", " ", text_to_split).split()

    for checked_word in input_words_list:
        checked_word_lower = checked_word.lower().removesuffix("-то").removesuffix("-ка").removesuffix("-таки").removeprefix("таки-")
        if checked_word_lower == "":
            continue

        string_to_add = ""
        cursor.execute("SELECT " + id_native + ", `" + id_inexact + "` FROM rodno_data WHERE " + id_non_native + "='" + checked_word_lower + "'")
        fix_recommendation = cursor.fetchone()
        if fix_recommendation is not None:
            string_not = "Не \"" if fix_recommendation[1] is None else "Вероятно не \""
            string_to_add = string_not + checked_word_lower + "\", а " + fix_recommendation[0] + "."
            string_to_add += "\n" if fix_recommendation[1] is None else " Если вы, конечно, не имели в виду " + fix_recommendation[1] + ".\n"
        else:
            for normal_form in morph.normal_forms(checked_word_lower):
                cursor.execute("SELECT " + id_native + ", `" + id_inexact + "`, `" + id_exclusions +
                               "` FROM rodno_data WHERE " + id_non_native + "='" + normal_form + "'")
                fix_recommendation = cursor.fetchone()
                if fix_recommendation is not None:
                    if fix_recommendation[2] is not None:  # if there are some excluded words
                        excls = fix_recommendation[2].split(',')
                        excls_stripped = [s.strip(" {}") for s in excls]
                        if checked_word_lower in excls_stripped:  # if current word is exclusion
                            break
                    string_not = "Не \"" if fix_recommendation[1] is None else "Вероятно не \""
                    string_to_add = string_not + normal_form + "\", а " + fix_recommendation[0] + "."
                    string_to_add += "\n" if fix_recommendation[1] is None else " Если вы, конечно, не имели в виду " + fix_recommendation[1] + ".\n"
                    break
        if string_to_add != "":
            if not (string_to_add in output_message):  #optimization (maybe)
                output_message += string_to_add

    cursor.close()
    conn.close()

    if output_message != "":
        output_message += "\n"
        lines = open("data/answers.txt", "r", encoding="utf-8").readlines()
        lines_ex = open("data/answers_extra.txt", "r", encoding="utf-8").readlines()
        rnd_val = random.randint(0, len(lines)-1)
        rnd_extra = random.randint(0, len(lines_ex)-1)
        if (update.message.from_user.username == 'Tatsuya_S') and (update.message.chat.type != 'private'):
            if "#" in lines_ex[rnd_extra]:
                lines_ex[rnd_extra] = lines_ex[rnd_extra].replace("#", update.message.from_user.first_name if random.randint(1, 2) == 1 else "@" + update.message.from_user.username)
            output_message += lines_ex[rnd_extra]
        elif update.message.chat.type == 'private':
            output_message += lines[0]
        else:
            if "#" in lines[rnd_val]:
                lines[rnd_val] = lines[rnd_val].replace("#", update.message.from_user.first_name if (random.randint(1, 2) == 1) | (update.message.from_user.username is None) else "@" + update.message.from_user.username)
            output_message += lines[rnd_val]
        update.message.reply_text(output_message)
    elif update.message.chat.type == 'private':
        output_message = "Языковая дружина проверила ваши письмена и не нашла ничего зазорного. Ладный русский слог, иностранщина не обнаружена, отпускаем вас."
        update.message.reply_text(output_message)


def main():
    """Start the bot."""
    updater = Updater(os.getenv("TG_API_KEY") if ('TG_API_KEY' in os.environ) else config.api_key)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('kak', message_how))
    dp.add_handler(CommandHandler('sved', message_info))
    dp.add_handler(CommandHandler('vzvod', change_react_frequency))
    dp.add_handler(MessageHandler((Filters.text | Filters.caption) & ((~Filters.forwarded) & (~Filters.chat_type.channel) | Filters.chat_type.private),
                                  process_text, pass_user_data=True))

    if 'TG_API_KEY' in os.environ:  # if prod
        updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=os.getenv("TG_API_KEY"),
                              webhook_url='https://korni-russkogo.herokuapp.com/' + os.getenv("TG_API_KEY"))
    else:  # if dev
        updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
