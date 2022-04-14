import re
import pymorphy2
import mysql.connector
import os
import sys
import random
import string
import urllib.parse as urlparse
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from telegram import ChatMember

try:
    import config
except ModuleNotFoundError:
    # if no config (i.e. prod)
    pass

PORT = int(os.environ.get('PORT', 5000))
morph = pymorphy2.MorphAnalyzer()
id_chat_id = "chat_id"
id_chat_caption = "chat_caption"
id_chat_username = "username"
id_freq = "freq"
id_exhortation = "exhortation"
id_non_native = "МУСОРНОЕ"
id_native = "РОДНОЕ"
id_exclusions = "ИСКЛЮЧЁННЫЕ ИСКАЖЕНИЯ"
id_inexact = "ПОПРАВКА НА СЛУЧАЙ НЕМУСОРНОГО"
id_extra_normal_form = "ДОП. РАСПОЗНАВАЕМОЕ ИСХОДНОЕ ИСКАЖЕНИЕ"
id_unrecognized_forms = "НЕРАСПОЗНАВАЕМЫЕ ИСКАЖЕНИЯ"


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
                                              host=url.hostname)
        else:
            connect = mysql.connector.connect(database=config.db_name, user=config.db_user, password=config.db_password,
                                              host=config.db_host)
    except mysql.connector.Error as e:
        print('Unable to connect!\n{0}').format(e)
        connect = None
    finally:
        return connect


def get_chat_frequency(cht_id):
    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor(buffered=True)
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


def get_chat_exhortation(cht_id):
    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor(buffered=True)
    else:
        sys.exit(1)
    cursor.execute("SELECT exhortation FROM freq_data WHERE chat_id='" + str(cht_id) + "'")
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if res is not None:
        return res[0]
    else:
        return res


def change_react_frequency(update, context):  # Process when the command /vzvod is issued.
    def send_message_when_wrong_argument():
        update.message.reply_text("Используйте целое числовое значение в промежутке от 1 до 50 в строке после приказа "
                                  "/vzvod и пробела для настройки ретивости робота в данной болталке.\nНапример: "
                                  "\"/vzvod 1\" - взводиться всегда, \"/vzvod 2\" - взводиться на каждое второе "
                                  "сообщение, \"/vzvod 10\" - взводиться на каждое десятое и т.п.")
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
    set_chat_frequency(param, update)
    update.message.reply_text("Ретивость робота в данной болталке установлена на " +
                              f'{100/param:4.2f}'.replace('.', ',') + "%")


def change_private_exhortation_mode(update, context):  # Process when the command /nazid is issued.
    def send_message_when_wrong_argument():
        update.message.reply_text("Используйте следующие значения в строке после приказа "
                                  "/nazid и пробела для настройки вида назиданий:\n"
                                  "\"/nazid korni\" - всегда назидание вида \"берегите корни\" (по умолчанию),\n" 
                                  "\"/nazid vse\" - все виды назиданий (так же, как в болталках),\n"
                                  "\"/nazid net\" - назидания не добавляются.")
    if update.message is None:
        return
    if update.message.chat.type != "private":
        update.message.reply_text("Настройка вида назиданий доступна только в личке, а не в болталках!")
        return
    if len(context.args) > 0:
        try:
            param = context.args[0]
        except ValueError:
            send_message_when_wrong_argument()
            return
    else:
        send_message_when_wrong_argument()
        return
    match param:
        case "korni":
            value = 0
            str_reply = "установлены по умолчанию"
        case "vse":
            value = 1
            str_reply = "включены полностью"
        case "net":
            value = 2
            str_reply = "выключены полностью"
        case _:
            send_message_when_wrong_argument()
            return
    set_private_chat_exhortation(value, update)
    update.message.reply_text("Назидания робота в личной переписке " + str_reply + ".")


def set_chat_frequency(fq, update):
    conn = connect_to_db()
    if conn is not None:
        cursor = conn.cursor(buffered=True)
    else:
        sys.exit(1)

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
        "INSERT INTO freq_data(" + id_chat_id + "," + id_chat_caption + "," + id_chat_username + "," + id_freq + "," + id_exhortation +
        ") VALUES(" + str(chat_id) + ", '" + title + "', '" + username + "', " + str(fq) + ", 1) " +
        "ON DUPLICATE KEY UPDATE " +
        id_chat_caption + "='" + title + "', " + id_chat_username + "='" + username + "', " + id_freq + "=" + str(fq) + ", " + id_exhortation + "=NULL")

    conn.commit()
    cursor.close()
    conn.close()


def set_private_chat_exhortation(val, update):
        conn = connect_to_db()
        if conn is not None:
            cursor = conn.cursor(buffered=True)
        else:
            sys.exit(1)

        chat_id = update.effective_chat.id
        title = "PRIVATE"
        user_username = update.effective_user.username
        username = "@" + user_username if (user_username is not None) else update.effective_user.first_name

        cursor.execute(
            "INSERT INTO freq_data(" + id_chat_id + "," + id_chat_caption + "," + id_chat_username + "," + id_freq + "," + id_exhortation +
            ") VALUES(" + str(chat_id) + ", '" + title + "', '" + username + "', 1, " + str(val) + ") " +
            "ON DUPLICATE KEY UPDATE " +
            id_chat_caption + "='" + title + "', " + id_chat_username + "='" + username + "', " + id_freq + "=NULL, " + id_exhortation + "=" + str(val))

        conn.commit()
        cursor.close()
        conn.close()


def correction_string(incoming_word, correction, exclusion):
    string_not = "Не \"" if exclusion is None else "Вероятно не \""
    string_res = string_not + incoming_word + "\", а " + correction + "."
    string_res += "\n" if exclusion is None else " Если вы, конечно, не имели в виду " + exclusion + ".\n"
    return string_res


def correction_string_from_normal_forms(crsr, chkd_wrd_lwr):
    string_res = ""
    for normal_form in morph.normal_forms(chkd_wrd_lwr):
        crsr.execute("SELECT " + id_native + ", `" + id_inexact + "`, `" + id_exclusions + "`, " + id_non_native +
                     " FROM rodno_data WHERE " +
                     id_non_native + "='" + normal_form + "' OR `" + id_extra_normal_form + "`='" + normal_form + "'")
        fix_recommendation = crsr.fetchone()
        if fix_recommendation is not None:
            if fix_recommendation[2] is not None:  # if there are some excluded words
                excls = fix_recommendation[2].split(',')
                excls_stripped = [s.strip(" {}") for s in excls]
                if chkd_wrd_lwr in excls_stripped:  # if current word is exclusion
                    break
            string_res = correction_string(fix_recommendation[3], fix_recommendation[0], fix_recommendation[1])
            break
    return string_res


# Let's analyze all the incoming text
def process_text(update, context):
    if update.message is None:
        return

    chat_id = update.effective_chat.id

    if update.message.chat.type != "private":
        current_freq = get_chat_frequency(chat_id)
        if current_freq is None:
            current_freq = 1
            set_chat_frequency(current_freq, update)
        else:
            is_no_message_process = (random.randint(1, current_freq) != 1)
            if is_no_message_process:
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
        cursor = conn.cursor(buffered=True)
    else:
        sys.exit(1)

    output_message = ""
    text_to_split = text_to_split.encode('cp1251', 'ignore').decode('cp1251')

    # let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    # [\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w-]", " ", text_to_split).split()

    for checked_word in input_words_list:
        checked_word_lower = checked_word.lower().removesuffix("-то").removesuffix("-ка").removesuffix("-таки").removeprefix("таки-")
        if checked_word_lower == "":
            continue
        cursor.execute("SELECT " + id_native + ", `" + id_inexact + "`, " + id_non_native + " FROM rodno_data WHERE " +
                       id_non_native + "='" + checked_word_lower +
                       "' OR LOCATE(' " + checked_word_lower + ",', `" + id_unrecognized_forms + "`)")
        fix_recommendation = cursor.fetchone()
        if fix_recommendation is not None:
            string_to_add = correction_string(fix_recommendation[2], fix_recommendation[0], fix_recommendation[1])
        else:
            string_to_add = correction_string_from_normal_forms(cursor, checked_word_lower)

        if string_to_add == "":  # check for word parts divided by '-'
            splitted_incoming_words = checked_word_lower.split('-')
            if len(splitted_incoming_words) > 1:
                for splitted_part in splitted_incoming_words:
                    if splitted_part in ["го", "ок"]:
                        continue
                    cursor.execute("SELECT " + id_native + ", `" + id_inexact + "`, " + id_non_native +
                                   " FROM rodno_data WHERE " + id_non_native + "='" + splitted_part +
                                   "' OR LOCATE(' " + splitted_part + ",', `" + id_unrecognized_forms + "`)")
                    fix_recommendation = cursor.fetchone()
                    if fix_recommendation is not None:
                        corr_str = correction_string(fix_recommendation[2], fix_recommendation[0], fix_recommendation[1])
                        if not (corr_str in output_message) and not (corr_str in string_to_add):
                            string_to_add += corr_str
                    else:
                        corr_str = correction_string_from_normal_forms(cursor, splitted_part)
                        if not (corr_str in output_message) and not (corr_str in string_to_add):
                            string_to_add += corr_str

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
            exhortation = get_chat_exhortation(chat_id)
            match exhortation:
                case None:
                    set_private_chat_exhortation(0, update)
                    output_message += lines[0]
                case 0:
                    output_message += lines[0]
                case 1:
                    pos_sharp = lines[rnd_val].find('#')
                    if pos_sharp != -1:
                        for i in range(pos_sharp - 1, -1, -1):
                            if lines[rnd_val][i] in string.punctuation or lines[rnd_val][i] == ' ':
                                if lines[rnd_val][i] in [',', ':', ';']:
                                    lines[rnd_val] = lines[rnd_val][0:i] + lines[rnd_val][pos_sharp + 1:len(lines[rnd_val])]
                                    break
                            else:
                                break
                    output_message += lines[rnd_val]
                case 2:
                    output_message = output_message.removesuffix("\n")
        else:
            if "#" in lines[rnd_val]:
                lines[rnd_val] = lines[rnd_val].replace("#", update.message.from_user.first_name if (random.randint(1, 2) == 1) | (update.message.from_user.username is None) else "@" + update.message.from_user.username)
            output_message += lines[rnd_val]
        if len(output_message) > 4096:
            update.message.reply_text(output_message[0:4096])
        else:
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
    dp.add_handler(CommandHandler('nazid', change_private_exhortation_mode))
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
