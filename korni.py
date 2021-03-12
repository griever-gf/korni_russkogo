import re
import pymorphy2
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import itertools
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
import logging
try:
    import config
except ModuleNotFoundError:
    # if no config (i.e. prod)
    pass

PORT = int(os.environ.get('PORT', 5000))
morph = pymorphy2.MorphAnalyzer()

def start_message(update, context):
    #Send a message when the command /start is issued.
    update.message.reply_text('Привет, добавь меня в любую болталку, будет круто. Ну или на крайний случай шли письмена в личку')

def read_glossary_data():
    # define the scope
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # add credentials to the account
    if ('GOOGLE_SHEETS_CREDS_JSON' in os.environ):  # if prod
        json_creds = os.getenv("GOOGLE_SHEETS_CREDS_JSON")
        creds_dict = json.loads(json_creds)
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else: #if dev
        creds = ServiceAccountCredentials.from_json_keyfile_name(config.json_keyfile_rodno, scope)

    # authorize the clientsheet
    client = gspread.authorize(creds)

    # get the instance of the Spreadsheet
    sheet = client.open('Корни языка')

    # get the first sheet of the Spreadsheet
    sheet_instance = sheet.get_worksheet(0)

    # get all the records of the data
    glossary_data = sheet_instance.get_all_records() #list of dictionaries
    key_incorrect = sheet_instance.cell(col=1,row=1).value #ключ мусорного значения
    key_correct = sheet_instance.cell(col=2,row=1).value #ключ родного значения

    return glossary_data, key_incorrect,  key_correct

def process_glossary_data (glossary_data, key_incorrect):
    for idxx, dict1 in enumerate(glossary_data):
        # split cell if in consist several words using re.sub(pattern, repl, string, count=0, flags=0)
        dict_words_list = re.split("[^\w\-\)\(]*\,[^\w\-\)\(]*", dict1[key_incorrect]) # split by comma + non-word chars minus brackets

        # if contains several round brackets, then generate several words instead source word
        i = 0
        while i < len(dict_words_list):
            list_of_inbrackets = re.findall("\([\w-]*\)", dict_words_list[i], re.IGNORECASE)
            if any(list_of_inbrackets):
                list_of_parts = re.split("\([\w-]*\)", dict_words_list[i], flags=re.IGNORECASE)
                list_of_replacement_variants = []
                for inbracket in list_of_inbrackets:
                    list_of_replacement_variants.append(("", inbracket.strip(')(')))

                dict_words_list.remove(dict_words_list[i])
                for trpl in itertools.product(*list_of_replacement_variants):
                    res_list = [list_of_parts[0]]
                    for j, content in enumerate(trpl):
                        res_list.append(content)
                        res_list.append(list_of_parts[j + 1])
                    dict_words_list.insert(i, ''.join(res_list))
                    i += 1
                i -= 1
            i += 1

        # if contains hyphens, then generate two words instead source word
        i = 0
        while i < len(dict_words_list):
            if "-" in dict_words_list[i]:
                extra_word = dict_words_list[i].replace("-", "")
                dict_words_list.insert(i + 1, extra_word)
            i += 1
        """
        # if contains several russian "е/э", then generate several words instead source word
        i = 0
        while i < len(dict_words_list):
            if any(re.findall(r'е|э', dict_words_list[i], re.IGNORECASE)):
                keyletters = 'еэ'
                # Convert input string into a list so we can easily substitute letters
                seq = list(dict_words_list[i])
                # Find indices of key letters in seq
                indices = [indx for indx, c in enumerate(seq) if c in keyletters]

                dict_words_list.remove(dict_words_list[i])
                # Generate key letter combinations & place them into the list
                for t in itertools.product(keyletters, repeat=len(indices)):
                    for j, c in zip(indices, t):
                        seq[j] = c
                    dict_words_list.insert(i, ''.join(seq))
                    i += 1
                i -= 1
            i += 1

        # if contains several russian "ф/фф", then generate several words instead source word
        i = 0
        while i < len(dict_words_list):
            if any(re.findall(r'ф', dict_words_list[i], re.IGNORECASE)):
                list_of_parts = re.split("ф+", dict_words_list[i], flags=re.IGNORECASE)

                dict_words_list.remove(dict_words_list[i])
                for trpl in itertools.product(["ф", "фф"], repeat=len(list_of_parts) - 1):
                    res_list = [list_of_parts[0]]
                    for j, content in enumerate(trpl):
                        res_list.append(content)
                        res_list.append(list_of_parts[j+1])
                    dict_words_list.insert(i, ''.join(res_list))
                    i += 1
                i -= 1
            i += 1
        """ """
        strout = "dict_words_list: "
        for non_native_word in dict_words_list:
            strout += non_native_word + " "
        print(strout)
        """
        glossary_data[idxx][key_incorrect] = ', '.join(dict_words_list)
    return glossary_data

#Let's analyze all the incoming text
def process_text(update, context):
    records_data, id_non_native, id_native = read_glossary_data()
    records_data = process_glossary_data(records_data, id_non_native)

    output_message = ""

    text_to_split = update.message.caption if (update.message.text is None) else update.message.text
    #print(text_to_split)

    # let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    # [\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w-]", " ", text_to_split).split()
    # print(input_words_list)

    for checked_word in input_words_list:
        # print("Проверяем: " + checked_word)
        # print(morph.parse(checked_word)[0].lexeme)
        # morph.parse(checked_word)[0].lexeme

        checked_word_lower = checked_word.lower().removesuffix("-то").removesuffix("-ка").removesuffix("-таки")

        string_to_add = ""
        # opening google sheet data
        for dict2 in records_data:
            # print(dict[id_non_native])
            # split cell if in consist several words using re.sub(pattern, repl, string, count=0, flags=0)
            # split by comma only (useful for words with spaces)
            dict_words_list = re.split("[^\w-]*,[^\w-]*", dict2[id_non_native]) #split by comma + non-word chars
            is_coincidence_found = False
            for non_native_word in dict_words_list:
                non_native_word = non_native_word.lower()
                # maybe should try to normalize non_native form too or to check all the forms of non_native_word
                if (checked_word_lower == non_native_word):
                    # print("Входное: " + checked_word)
                    # print("Попробуйте: " + dict2[id_native])
                    string_to_add = "Не \"" + checked_word_lower + "\", а " + dict2[id_native] + ".\n"
                    is_coincidence_found = True
                    break
                else:
                    for normal_form in morph.normal_forms(checked_word_lower):
                        if (normal_form == non_native_word):
                            string_to_add = "Не \"" + normal_form + "\", а " + dict2[id_native] + ".\n"
                            is_coincidence_found = True
                            break
                    if (is_coincidence_found):
                        break
            if (is_coincidence_found):
                break
        #check for identical incoming words - they don't need to appear several times in response message
        if (string_to_add != ""):
            if (not (string_to_add in output_message)): #optimization (maybe)
                output_message += string_to_add

    if (output_message != ""):
        output_message += "Берегите корни русского языка..."
        update.message.reply_text(output_message)

def main():
    """Start the bot."""
    updater = Updater(os.getenv("TG_API_KEY") if ('TG_API_KEY' in os.environ) else config.api_key)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start_message))
    dp.add_handler(MessageHandler((Filters.text | Filters.caption) & ((~Filters.forwarded) | Filters.private), process_text))

    if ('TG_API_KEY' in os.environ):  # if prod
        updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=os.getenv("TG_API_KEY"))
        updater.bot.setWebhook('https://korni-russkogo.herokuapp.com/' + os.getenv("TG_API_KEY"))
    else: #if dev
        updater.start_polling()

    updater.idle()

if __name__ == '__main__':
    main()
