import pyxel
import csv
import json
import random
import os
import re

# --- スクリプトと同じフォルダを基準にする ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WORDS_CSV = os.path.join(BASE_DIR, "words_lv01.csv")
FONT_12 = os.path.join(BASE_DIR, "umplus_j12r.bdf")
FONT_10 = os.path.join(BASE_DIR, "umplus_j10r.bdf")

# ------------------------------------------------------------------
# セーブデータの保存先について
#
# Pyxel Web（ブラウザ版）はGitHub Pagesのような静的ホスティング上で動くため、
# 通常のファイル書き込みではブラウザに保存した内容を後から読み直せない
# （読み込みがサーバーへのHTTP取得として扱われ、書いたファイルが404になる）。
#
# Pyxel WebはPyodide（ブラウザ上のCPython）で動いているため、
# `from js import localStorage` でブラウザのlocalStorageに直接アクセスできる。
# これはページを閉じても消えない、ブラウザ本来の保存領域なので、
# ハイスコアや間違えた単語のような「セーブデータ」はこちらに保存する。
#
# ローカル（PC）で `pyxel run` する場合は js モジュールが無いので、
# 従来通りファイルに保存する（SAVE_DIR）。
# ------------------------------------------------------------------
_local_storage = None
HAS_LOCAL_STORAGE = False
try:
    from js import localStorage as _local_storage
    HAS_LOCAL_STORAGE = True
except Exception as e:
    print(f"[EnglishWord] 'from js import localStorage' に失敗: {e}")
    try:
        import js as _js_module
        _local_storage = _js_module.localStorage
        HAS_LOCAL_STORAGE = True
    except Exception as e2:
        print(f"[EnglishWord] 'import js; js.localStorage' も失敗: {e2}")
        print("[EnglishWord] localStorageが使えないため、ファイル保存にフォールバックします")

print(f"[EnglishWord] HAS_LOCAL_STORAGE = {HAS_LOCAL_STORAGE}")

STORAGE_PREFIX = "englishword1900."


def storage_get(key, default=None):
    """セーブデータを1件読み込む（Web版はlocalStorage、ローカルはファイル）。"""
    if HAS_LOCAL_STORAGE:
        try:
            raw = _local_storage.getItem(STORAGE_PREFIX + key)
            if raw is None:
                return default
            return json.loads(raw)
        except Exception as e:
            print(f"localStorageの読み込みに失敗しました ({key}): {e}")
            return default
    else:
        path = os.path.join(SAVE_DIR, key + ".json")
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"セーブファイルの読み込みに失敗しました ({path}): {e}")
            return default


def storage_set(key, value):
    """セーブデータを1件保存する（Web版はlocalStorage、ローカルはファイル）。"""
    if HAS_LOCAL_STORAGE:
        try:
            _local_storage.setItem(STORAGE_PREFIX + key, json.dumps(value, ensure_ascii=False))
        except Exception as e:
            print(f"localStorageへの保存に失敗しました ({key}): {e}")
    else:
        ensure_save_dir()
        path = os.path.join(SAVE_DIR, key + ".json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)
        except Exception as e:
            print(f"セーブファイルの保存に失敗しました ({path}): {e}")


def resolve_save_dir():
    """（ローカル実行時のみ使用）実際に書き込み・読み込みができる保存先を探して返す。"""
    candidates = []
    try:
        candidates.append(os.path.abspath(pyxel.user_data_dir(VENDOR_NAME, APP_NAME)))
    except Exception as e:
        print(f"user_data_dir の取得に失敗しました: {e}")
    candidates.append(BASE_DIR)
    candidates.append(os.path.abspath("."))

    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, ".savetest")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            with open(test_file, encoding="utf-8") as f:
                content = f.read()
            os.remove(test_file)
            if content == "ok":
                return path
        except Exception as e:
            print(f"保存先候補として使えませんでした ({path}): {e}")

    print("有効な保存先が見つからなかったため、スクリプトと同じ場所を使います")
    return BASE_DIR


SAVE_DIR = BASE_DIR
VENDOR_NAME = "kazu_home_page"
APP_NAME = "EnglishWord1900"


def ensure_save_dir():
    """SAVE_DIR が確実に存在するようにする（ローカル実行時の保険）。"""
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
    except OSError as e:
        print(f"保存フォルダの作成に失敗しました: {e}")


PLAYERS = ["ゆそ", "しん", "キャス", "ファザ", "ゲスト"]


def migrate_legacy_local_files():
    """以前のバージョン（CSVファイルに直接保存する方式）で貯めたローカルの
    ハイスコア・間違えた単語・復習記録が残っていたら、新しい保存方式に
    一度だけ取り込む（ローカル実行時のみ。Web版はそもそも対象データが無い）。"""
    if HAS_LOCAL_STORAGE:
        return

    # ranking.csv -> ranking
    legacy_ranking = os.path.join(SAVE_DIR, "ranking.csv")
    if os.path.exists(legacy_ranking) and storage_get("ranking") is None:
        rows = []
        try:
            with open(legacy_ranking, encoding="utf-8") as f:
                for row in csv.reader(f):
                    if len(row) >= 2:
                        try:
                            rows.append([row[0].strip(), int(row[1].strip())])
                        except ValueError:
                            continue
        except OSError as e:
            print(f"旧ランキングの読み込みに失敗しました: {e}")
        if rows:
            storage_set("ranking", rows)
            print(f"[EnglishWord] 旧形式のランキングを取り込みました（{len(rows)}件）")

    for player in PLAYERS:
        # missed_words_<player>.csv -> missed_words.<player>
        legacy_missed = os.path.join(SAVE_DIR, f"missed_words_{player}.csv")
        missed_key = f"missed_words.{player}"
        if os.path.exists(legacy_missed) and storage_get(missed_key) is None:
            rows = []
            try:
                with open(legacy_missed, encoding="utf-8") as f:
                    for row in csv.reader(f):
                        if len(row) >= 2:
                            rows.append([row[0].strip(), row[1].strip()])
            except OSError as e:
                print(f"{player}さんの旧・間違えた単語の読み込みに失敗しました: {e}")
            if rows:
                storage_set(missed_key, rows)
                print(f"[EnglishWord] {player}さんの旧・間違えた単語を取り込みました（{len(rows)}件）")

        # review_stats_<player>.csv -> review_stats.<player>
        legacy_review = os.path.join(SAVE_DIR, f"review_stats_{player}.csv")
        review_key = f"review_stats.{player}"
        if os.path.exists(legacy_review) and storage_get(review_key) is None:
            raw = {}
            try:
                with open(legacy_review, encoding="utf-8") as f:
                    for row in csv.reader(f):
                        if len(row) >= 3:
                            try:
                                raw[f"{row[0].strip()}\t{row[1].strip()}"] = int(row[2].strip())
                            except ValueError:
                                continue
            except OSError as e:
                print(f"{player}さんの旧・復習記録の読み込みに失敗しました: {e}")
            if raw:
                storage_set(review_key, raw)
                print(f"[EnglishWord] {player}さんの旧・復習記録を取り込みました")


# --- 選択肢ボタンに使う、ぱきっと明るいカラーパレット（順番に回して使う） ---
CHOICE_COLORS = [
    pyxel.COLOR_PINK,
    pyxel.COLOR_LIGHT_BLUE,
    pyxel.COLOR_LIME,
    pyxel.COLOR_ORANGE,
    pyxel.COLOR_CYAN,
    pyxel.COLOR_PEACH,
]

STATE_PLAYER_SELECT = "player_select"
STATE_START = "start"
STATE_PLAY = "play"
STATE_RESULT = "result"

MODE_NORMAL = "normal"
MODE_REVIEW = "review"
MODE_TIMEATTACK = "timeattack"

REVIEW_QUESTIONS = 10
REVIEW_MASTERY_COUNT = 5  # 復習で連続して正解できたら卒業させる回数

FPS = 30
TIME_ATTACK_SECONDS = 5 * 60


# ------------------------------------------------------------------
# 単語データ
#
# words_lvXX.csv は行によって形式が違う。1行ずつ「列の意味」を判断して
# WordBasic（英単語→日本語の意味を選ぶ、従来形式）か
# WordQuiz（空所補充などの4択英文問題、新形式）のどちらかを作る。
#
#   2列: english, japanese
#   3列: english, japanese, note
#   4列: english, japanese, example_en, example_ja
#   7列: question, choice1, choice2, choice3, choice4, answer, japanese
# ------------------------------------------------------------------
class WordBasic:
    __slots__ = ("english", "japanese", "example_en", "example_ja", "note")

    def __init__(self, english, japanese, example_en=None, example_ja=None, note=None):
        self.english = english
        self.japanese = japanese
        self.example_en = example_en
        self.example_ja = example_ja
        self.note = note

    def prompt(self):
        return f"英単語: {self.english}"

    def choice_pool_key(self):
        return self.japanese

    def correct_choice(self):
        return self.japanese

    def save_key(self):
        return (self.english, self.japanese)

    def to_missed_record(self):
        return {"type": "basic", "english": self.english, "japanese": self.japanese}


class WordQuiz:
    __slots__ = ("question", "choices", "answer", "japanese")

    def __init__(self, question, choices, answer, japanese):
        self.question = question
        self.choices = list(choices)
        self.answer = answer
        self.japanese = japanese

    def prompt(self):
        return self.question

    def correct_choice(self):
        return self.answer

    def save_key(self):
        return (self.question, self.answer)

    def to_missed_record(self):
        return {"type": "quiz", "question": self.question, "choices": self.choices,
                "answer": self.answer, "japanese": self.japanese}


def word_from_missed_record(item):
    """間違えた単語の保存データ1件から、WordBasic/WordQuizを復元する。
    以前のバージョンの保存形式（[english, japanese] のリスト）にも対応する。"""
    if isinstance(item, dict):
        if item.get("type") == "quiz":
            choices = item.get("choices") or []
            question = item.get("question")
            answer = item.get("answer")
            if len(choices) == 4 and question and answer:
                if answer not in choices:
                    print(f"[EnglishWord] 復習データの4択問題で、正解が選択肢に無いため無効化します: "
                          f"question={question!r} answer={answer!r} choices={choices!r}")
                    return None
                return WordQuiz(question, choices, answer, item.get("japanese", ""))
            return None
        english = item.get("english")
        japanese = item.get("japanese")
        if english and japanese:
            return WordBasic(english, japanese)
        return None
    if isinstance(item, list) and len(item) >= 2:
        return WordBasic(item[0], item[1])
    return None


# 後方互換のため（過去のコードやセーブデータが Word を参照していても動くように）
Word = WordBasic


# --- 単語読み込み（words_lv01.csv などの「読み込み専用」の単語帳） ---
def load_words(filename=WORDS_CSV):
    words = []
    if not os.path.exists(filename):
        return words

    with open(filename, encoding="utf-8") as f:
        reader = csv.reader(f)
        for line_no, row in enumerate(reader, start=1):
            row = [c.strip() for c in row]
            # 末尾の空セル（行末の余分なカンマなど）は無視する
            while row and row[-1] == "":
                row.pop()
            n = len(row)

            if n == 7:
                question, c1, c2, c3, c4, answer, japanese = row
                choices = [c1, c2, c3, c4]
                if not (question and answer and japanese):
                    print(f"{filename}:{line_no} 4択問題の必須項目が空です。スキップします: {row}")
                elif answer not in choices:
                    print(f"{filename}:{line_no} 4択問題の正解が選択肢の中にありません。"
                          f"スキップします: answer={answer!r} choices={choices!r}")
                else:
                    words.append(WordQuiz(question, choices, answer, japanese))
            elif n == 2:
                english, japanese = row
                if english and japanese:
                    words.append(WordBasic(english, japanese))
            elif n == 3:
                english, japanese, note = row
                if english and japanese:
                    words.append(WordBasic(english, japanese, note=note))
            elif n == 4:
                english, japanese, example_en, example_ja = row
                if english and japanese:
                    words.append(WordBasic(english, japanese, example_en=example_en, example_ja=example_ja))
            elif n == 0:
                continue  # 空行
            else:
                print(f"{filename}:{line_no} 列数が想定外（{n}列）のためスキップします: {row}")

    return words


def _safe_player_key(player):
    return player if player else "unknown"


# --- 間違えた単語（プレイヤーごと） ---
def load_missed_words_unique(player):
    """セーブデータから読み込み、Word系オブジェクト（WordBasic/WordQuiz）のリストにして返す。
    壊れている（正解が選択肢に無い等）レコードが見つかった場合は、保存データからも
    取り除いておく（同じ壊れた問題が繰り返し出てこないようにするため）。"""
    key = f"missed_words.{_safe_player_key(player)}"
    raw = storage_get(key, default=[])
    seen = {}
    had_invalid = False
    for item in raw:
        word = word_from_missed_record(item)
        if word is not None:
            seen[word.save_key()] = word
        else:
            had_invalid = True

    if had_invalid:
        cleaned = [w.to_missed_record() for w in seen.values()]
        storage_set(key, cleaned)
        print(f"[EnglishWord] {player}さんの間違えた単語リストから、壊れたデータを取り除きました")

    return list(seen.values())


def save_missed_word(word, player):
    """間違えた単語を保存する。word には WordBasic か WordQuiz のインスタンスを渡す。"""
    key = f"missed_words.{_safe_player_key(player)}"
    raw = storage_get(key, default=[])
    raw.append(word.to_missed_record())
    storage_set(key, raw)


def remove_missed_word(player, save_key):
    """復習をマスターした単語を「間違えた単語」リストから完全に削除する。"""
    key = f"missed_words.{_safe_player_key(player)}"
    raw = storage_get(key, default=[])
    new_raw = []
    for item in raw:
        word = word_from_missed_record(item)
        if word is not None and word.save_key() == save_key:
            continue  # この単語は卒業したので取り除く
        new_raw.append(item)
    storage_set(key, new_raw)


# --- 復習の連続正解数（プレイヤーごと） ---
def load_review_stats(player):
    raw = storage_get(f"review_stats.{_safe_player_key(player)}", default={})
    stats = {}
    for k, v in raw.items():
        parts = k.split("\t", 1)
        if len(parts) == 2:
            try:
                stats[(parts[0], parts[1])] = int(v)
            except (TypeError, ValueError):
                continue
    return stats


def save_review_stats(player, stats):
    key = f"review_stats.{_safe_player_key(player)}"
    raw = {f"{a}\t{b}": cnt for (a, b), cnt in stats.items()}
    storage_set(key, raw)


# --- タイムアタック用に、見つかる単語帳(words_lv01〜08.csv)を全部まとめて読み込む ---
def load_wordbank_all():
    combined = []
    for i in range(1, 9):
        fn = os.path.join(BASE_DIR, f"words_lv{i:02d}.csv")
        combined.extend(load_words(fn))
    if not combined:
        combined = load_words(WORDS_CSV)
    return combined


# --- ランキング（タイムアタックのスコア）読み込み・保存 ---
def load_ranking():
    raw = storage_get("ranking", default=[])
    rows = []
    for item in raw:
        if isinstance(item, list) and len(item) >= 2:
            try:
                rows.append((item[0], int(item[1])))
            except (TypeError, ValueError):
                continue
    return rows


def save_ranking_entry(player, score):
    raw = storage_get("ranking", default=[])
    raw.append([player, score])
    storage_set("ranking", raw)


# --- ランキング表示用：プレイヤーごとの自己ベストだけを1件ずつ取り出す ---
def load_ranking_best_per_player():
    best = {}
    for player, score in load_ranking():
        if player not in best or score > best[player]:
            best[player] = score
    return sorted(best.items(), key=lambda kv: -kv[1])


# --- 例文中の対象単語を隠す ---
def mask_target_word(sentence, english):
    if not sentence:
        return None
    pattern = re.compile(r"\b" + re.escape(english) + r"\w*", re.IGNORECASE)

    def repl(m):
        return "_" * len(m.group(0))

    masked, n = pattern.subn(repl, sentence)
    if n == 0:
        return sentence
    return masked


# --- 文を指定幅で折り返す（1行に収まらない場合は "..." で省略） ---
def wrap_text(font, text, max_width, max_lines=1):
    words = text.split(" ")
    lines = []
    current = ""
    for w in words:
        candidate = w if not current else current + " " + w
        width = font.text_width(candidate) if font else len(candidate) * 4
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines:
        last = lines[-1]
        while (font.text_width(last + "...") if font else (len(last) + 3) * 4) > max_width and len(last) > 0:
            last = last[:-1]
        joined_len = sum(len(l) for l in lines)
        if joined_len < len(text.replace(" ", "")):
            lines[-1] = last + "..."
    return lines


class WordGame:
    SCREEN_W = 240
    SCREEN_H = 320

    CHOICE_X = 20
    CHOICE_W = 200
    CHOICE_GAP = 8
    CHOICES_END_Y = 272  # この位置より下にはボタンを描かない（メッセージ欄の手前まで）

    STREAK_TO_LEVEL_UP = 5
    MAX_CHOICES = 5

    HEADER_H = 64  # 上部のカラフルなヘッダー帯の高さ（拡大文字がはみ出さない余裕を確保）

    def __init__(self):
        self.normal_words = load_words()
        self.normal_wordlist_name = os.path.basename(WORDS_CSV)

        self.words = self.normal_words
        self.current_wordlist = self.normal_wordlist_name

        pyxel.init(self.SCREEN_W, self.SCREEN_H, title="英単語選択ゲーム（スマホ＋PC対応）", fps=FPS)
        pyxel.mouse(True)  # マウスカーソルを表示する

        global SAVE_DIR
        SAVE_DIR = resolve_save_dir()
        print(f"[EnglishWord] セーブデータの保存先: "
              f"{'localStorage' if HAS_LOCAL_STORAGE else SAVE_DIR}")
        migrate_legacy_local_files()

        # --- 日本語フォント読み込み（BDFフォント） ---
        self.font_l = None  # 見出し・選択肢用（12px）
        self.font_s = None  # スコア・メッセージ・例文用（10px）
        try:
            self.font_l = pyxel.Font(FONT_12)
            self.font_s = pyxel.Font(FONT_10)
        except Exception as e:
            print(f"フォント読み込みに失敗しました: {e}")

        self.player = None
        self.review_stats = {}

        # 画面の再描画のたびにセーブデータを読み直さないためのキャッシュ
        self.cached_missed_count = 0
        self.cached_best_scores = {}

        self.score_correct = 0
        self.score_total = 0
        self.level = 1
        self.streak = 0

        self.mode = MODE_NORMAL
        self.review_progress = 0
        self.saved_words = None
        self.saved_wordlist_name = None

        # --- タイムアタック関連 ---
        self.ta_correct = 0
        self.ta_wrong = 0
        self.ta_score = 0
        self.ta_combo = 0
        self.ta_best_combo = 0
        self.ta_start_frame = 0
        self.ta_duration_frames = TIME_ATTACK_SECONDS * FPS
        self.ta_final_score = 0
        self.ta_is_new_best = False
        self.ranking_rows = []

        self.word_changed = False
        self.word_change_timer = 0

        self.notice = ""
        self.notice_timer = 0

        rnd = random.Random(12345)
        self.bg_dots = [
            (rnd.randint(0, self.SCREEN_W), rnd.randint(self.HEADER_H + 10, self.SCREEN_H),
             rnd.choice([pyxel.COLOR_PINK, pyxel.COLOR_PEACH, pyxel.COLOR_LIGHT_BLUE]),
             rnd.randint(1, 2))
            for _ in range(18)
        ]

        self.go_to_player_select()
        self.reset_question()
        pyxel.run(self.update, self.draw)

    # ------------------------------------------------------------------
    # 大きく・くっきり見せるための拡大文字描画
    # ------------------------------------------------------------------
    def draw_big_text(self, x, y, s, col, font, scale=2, outline_col=None, font_h=16, max_width=None):
        if not s:
            return 0
        w = font.text_width(s)
        if max_width is not None:
            while scale > 1 and (w * 1.5) * scale > max_width:
                scale -= 1

        if scale <= 1:
            if outline_col is not None:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    pyxel.text(x + dx, y + dy, s, outline_col, font)
            pyxel.text(x, y, s, col, font)
            return w

        buf_w = max(1, w + 2)
        img = pyxel.Image(buf_w, font_h)
        img.cls(0)  # 0(黒)を透過色として使う（文字色に黒は使わない前提）
        if outline_col is not None:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                img.text(1 + dx, 2 + dy, s, outline_col, font)
        img.text(1, 2, s, col, font)

        for sy in range(font_h):
            for sx in range(buf_w):
                c = img.pget(sx, sy)
                if c == 0:
                    continue
                pyxel.rect(x + sx * scale, y + sy * scale, scale, scale, c)
        return w * scale

    def current_num_choices(self):
        return min(3 + self.level, self.MAX_CHOICES)

    def reset_question(self):
        if not self.words:
            self.correct_word = WordBasic("-", "（単語がありません）")
            self.choices = ["（単語がありません）"]
            self.example_en_lines = []
            self.example_ja_lines = []
            self.choices_start_y = self.HEADER_H + 58
            self.choice_h = 40
            self.message = ""
            self.message_col = pyxel.COLOR_WHITE
            self.cooldown = 0
            return

        word = random.choice(self.words)
        self.correct_word = word

        if isinstance(word, WordQuiz):
            self.choices = list(word.choices)
            random.shuffle(self.choices)
            self.example_en_lines = []
            self.example_ja_lines = []
        else:
            num_choices = min(self.current_num_choices(), len(self.words)) if self.mode == MODE_NORMAL else min(4, len(self.words))
            num_choices = max(2, num_choices)
            choices = {word.choice_pool_key()}
            tries = 0
            while len(choices) < num_choices and tries < 200:
                other = random.choice(self.words)
                if isinstance(other, WordQuiz):
                    tries += 1
                    continue
                choices.add(other.choice_pool_key())
                tries += 1

            self.choices = list(choices)
            random.shuffle(self.choices)

            self.example_en_lines = []
            if word.example_en:
                masked = mask_target_word(word.example_en, word.english)
                self.example_en_lines = wrap_text(self.font_s, masked, self.CHOICE_W, max_lines=2)

            self.example_ja_lines = []
            show_ja = self.mode == MODE_REVIEW or (self.mode == MODE_NORMAL and self.level < 2)
            if word.example_ja and show_ja:
                self.example_ja_lines = wrap_text(self.font_s, word.example_ja, self.CHOICE_W, max_lines=2)

        # --- レイアウト計算 ---
        content_y = self.HEADER_H + 38
        for _ in self.example_en_lines:
            content_y += 12
        if self.example_en_lines:
            content_y += 2
        for _ in self.example_ja_lines:
            content_y += 12
        if self.example_ja_lines:
            content_y += 4
        if isinstance(self.correct_word, WordQuiz):
            content_y += 24  # 問題文・日本語訳の分だけ余分にスペースを取る
        self.choices_start_y = max(self.HEADER_H + 58, content_y + 6)

        available_h = self.CHOICES_END_Y - self.choices_start_y
        n = len(self.choices)
        self.choice_h = max(20, (available_h - self.CHOICE_GAP * (n - 1)) // n)

        self.message = ""
        self.message_col = pyxel.COLOR_WHITE
        self.cooldown = 0

    def choice_rect(self, i):
        x = self.CHOICE_X
        y = self.choices_start_y + i * (self.choice_h + self.CHOICE_GAP)
        return x, y, self.CHOICE_W, self.choice_h

    def hovered_choice_index(self):
        mx, my = pyxel.mouse_x, pyxel.mouse_y
        for i in range(len(self.choices)):
            x, y, w, h = self.choice_rect(i)
            if x <= mx <= x + w and y <= my <= y + h:
                return i
        return -1

    # ------------------------------------------------------------------
    # プレイヤー選択画面
    # ------------------------------------------------------------------
    def player_select_rects(self):
        n = len(PLAYERS)
        cols = 2
        rows = (n + cols - 1) // cols
        gap = 8
        bw = (self.CHOICE_W - gap) // cols
        y0 = 110
        area_bottom = 286  # このY座標より下にはボタンを置かない（下の案内文の手前まで）
        available_h = area_bottom - y0
        bh = min(70, max(40, (available_h - gap * (rows - 1)) // rows))
        x0 = self.CHOICE_X
        rects = []
        for i in range(n):
            col = i % cols
            row = i // cols
            x = x0 + col * (bw + gap)
            y = y0 + row * (bh + gap)
            rects.append((x, y, bw, bh))
        return rects

    def update_player_select(self):
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            mx, my = pyxel.mouse_x, pyxel.mouse_y
            for name, (x, y, w, h) in zip(PLAYERS, self.player_select_rects()):
                if x <= mx <= x + w and y <= my <= y + h:
                    self.select_player(name)
                    return

    def refresh_missed_count(self):
        self.cached_missed_count = len(load_missed_words_unique(self.player))

    def refresh_best_scores(self):
        self.cached_best_scores = dict(load_ranking_best_per_player())

    def go_to_start(self):
        self.refresh_missed_count()
        self.state = STATE_START

    def go_to_player_select(self):
        self.refresh_best_scores()
        self.state = STATE_PLAYER_SELECT

    def select_player(self, name):
        self.player = name
        self.go_to_start()

    def draw_player_select(self):
        pyxel.cls(pyxel.COLOR_PEACH)
        for x, y, col, r in self.bg_dots:
            pyxel.circ(x, y, r, col)

        pyxel.rect(0, 0, self.SCREEN_W, self.HEADER_H, pyxel.COLOR_PINK)
        pyxel.rect(0, self.HEADER_H, self.SCREEN_W, 3, pyxel.COLOR_ORANGE)
        pyxel.clip(0, 0, self.SCREEN_W, self.HEADER_H)
        self.draw_big_text(16, 16, "だれがやる？", pyxel.COLOR_WHITE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_PURPLE, max_width=self.SCREEN_W - 24)
        pyxel.clip()

        button_colors = [pyxel.COLOR_LIME, pyxel.COLOR_LIGHT_BLUE, pyxel.COLOR_ORANGE,
                          pyxel.COLOR_PINK, pyxel.COLOR_CYAN]
        for name, (x, y, w, h), col in zip(PLAYERS, self.player_select_rects(), button_colors):
            pyxel.rect(x, y, w, h, col)
            pyxel.rectb(x, y, w, h, pyxel.COLOR_WHITE)
            pyxel.clip(x, y, w, h)
            self.draw_big_text(x + 6, y + 6, name, pyxel.COLOR_PURPLE, self.font_l,
                                scale=2, outline_col=pyxel.COLOR_WHITE, max_width=w - 10)
            score = self.cached_best_scores.get(name)
            score_text = f"Hi-Score:{score}" if score is not None else "記録なし"
            pyxel.text(x + 4, y + h - 12, score_text, pyxel.COLOR_WHITE, self.font_s)
            pyxel.clip()

        pyxel.text(20, 290, "タップして自分の名前を選んでね", pyxel.COLOR_GRAY, self.font_s)
        save_label = "localStorage" if HAS_LOCAL_STORAGE else SAVE_DIR
        pyxel.text(20, 306, f"save:{save_label}", pyxel.COLOR_GRAY, self.font_s)

    # ------------------------------------------------------------------
    # スタート画面
    # ------------------------------------------------------------------
    def start_screen_rects(self):
        normal_rect = (20, 100, self.CHOICE_W, 50)
        review_rect = (20, 158, self.CHOICE_W, 50)
        timeattack_rect = (20, 216, self.CHOICE_W, 50)
        return normal_rect, review_rect, timeattack_rect

    def player_switch_button_rect(self):
        return (self.SCREEN_W - 80, 4, 74, 16)

    def back_button_rect(self):
        return (self.SCREEN_W - 50, 4, 44, 16)

    def update_start(self):
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            mx, my = pyxel.mouse_x, pyxel.mouse_y

            bx, by, bw, bh = self.player_switch_button_rect()
            if bx <= mx <= bx + bw and by <= my <= by + bh:
                self.go_to_player_select()
                return

            normal_rect, review_rect, timeattack_rect = self.start_screen_rects()

            def hit(r):
                x, y, w, h = r
                return x <= mx <= x + w and y <= my <= y + h

            if hit(normal_rect):
                self.start_normal_mode()
            elif hit(review_rect):
                self.start_review_mode()
            elif hit(timeattack_rect):
                self.start_time_attack_mode()

    def start_normal_mode(self):
        self.mode = MODE_NORMAL
        self.words = self.normal_words
        self.current_wordlist = self.normal_wordlist_name
        self.state = STATE_PLAY
        self.reset_question()

    def start_review_mode(self):
        missed = load_missed_words_unique(self.player)
        if not missed:
            self.notice = "まだ復習できる単語がありません"
            self.notice_timer = 90
            return

        self.saved_words = self.words
        self.saved_wordlist_name = self.current_wordlist

        self.mode = MODE_REVIEW
        self.words = missed
        self.current_wordlist = "復習モード（間違えた単語）"
        self.review_progress = 0
        self.review_stats = load_review_stats(self.player)
        self.state = STATE_PLAY
        self.reset_question()

    def get_word_range(self):
        lv = self.level
        if lv <= 1:
            return (1, 1)
        elif lv == 2:
            return (1, 2)
        elif lv == 3:
            return (2, 3)
        elif lv == 4:
            return (3, 4)
        elif lv == 5:
            return (4, 5)
        elif lv == 6:
            return (5, 6)
        elif lv == 7:
            return (6, 7)
        elif lv == 8:
            return (7, 8)
        else:
            return (4, 8)  # Lv9以上

    def _load_word_range_pool(self):
        start_lv, end_lv = self.get_word_range()
        pool = []
        for i in range(start_lv, end_lv + 1):
            fn = os.path.join(BASE_DIR, f"words_lv{i:02d}.csv")
            pool.extend(load_words(fn))
        if not pool:
            pool = self.normal_words
        return pool, start_lv, end_lv

    def reload_timeattack_wordlist(self):
        pool, start_lv, end_lv = self._load_word_range_pool()
        self.words = pool
        self.current_wordlist = f"Lv{start_lv:02d}〜Lv{end_lv:02d}"

    def start_time_attack_mode(self):
        self.level = 1
        pool, start_lv, end_lv = self._load_word_range_pool()

        self.mode = MODE_TIMEATTACK
        self.words = pool
        self.current_wordlist = f"Lv{start_lv:02d}〜Lv{end_lv:02d}"

        self.ta_correct = 0
        self.ta_wrong = 0
        self.ta_score = 0
        self.ta_combo = 0
        self.ta_best_combo = 0
        self.ta_start_frame = pyxel.frame_count

        self.state = STATE_PLAY
        self.reset_question()

    def end_time_attack(self):
        final_score = self.ta_score
        self.ta_final_score = final_score

        prior = load_ranking()
        player_scores = [s for p, s in prior if p == self.player]
        player_best = max(player_scores) if player_scores else None
        self.ta_is_new_best = (player_best is None) or (final_score > player_best)

        save_ranking_entry(self.player, final_score)
        self.ranking_rows = load_ranking_best_per_player()[:5]

        self.state = STATE_RESULT

    def update_result(self):
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT) or pyxel.btnp(pyxel.KEY_R):
            self.mode = MODE_NORMAL
            self.words = self.normal_words
            self.current_wordlist = self.normal_wordlist_name
            self.go_to_start()

    def back_to_normal_after_review(self):
        self.mode = MODE_NORMAL

        self.score_correct = 0
        self.score_total = 0
        self.level = 1
        self.streak = 0

        self.normal_words = load_words(WORDS_CSV)
        self.normal_wordlist_name = os.path.basename(WORDS_CSV)
        self.words = self.normal_words
        self.current_wordlist = self.normal_wordlist_name

        self.saved_words = None
        self.saved_wordlist_name = None
        self.review_progress = 0
        self.notice = "通常モードを最初からやり直します"
        self.notice_timer = 90

    # ------------------------------------------------------------------
    def update(self):
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()

        if self.notice_timer > 0:
            self.notice_timer -= 1
            if self.notice_timer <= 0:
                self.notice = ""

        if self.state == STATE_PLAYER_SELECT:
            self.update_player_select()
            return

        if self.state == STATE_START:
            self.update_start()
            return

        if self.state == STATE_RESULT:
            self.update_result()
            return

        # ここから STATE_PLAY
        if pyxel.btnp(pyxel.KEY_R):
            self.go_to_start()
            return

        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            bx, by, bw, bh = self.back_button_rect()
            mx, my = pyxel.mouse_x, pyxel.mouse_y
            if bx <= mx <= bx + bw and by <= my <= by + bh:
                self.go_to_start()
                return

        if self.mode == MODE_TIMEATTACK:
            remaining = self.ta_duration_frames - (pyxel.frame_count - self.ta_start_frame)
            if remaining <= 0:
                self.end_time_attack()
                return

        if self.word_changed:
            self.word_change_timer -= 1
            if self.word_change_timer <= 0:
                self.word_changed = False
            return

        if self.cooldown > 0:
            self.cooldown -= 1
            return

        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            i = self.hovered_choice_index()
            if i >= 0:
                self.check_answer(self.choices[i])

    # ------------------------------------------------------------------
    # 正解判定は WordBasic / WordQuiz どちらでも同じ経路を通る。
    # （タイムアタックのスコア・コンボや、通常モードのレベルアップ、
    #   復習の卒業判定などが、問題の種類に関係なく必ず効くようにするため）
    # ------------------------------------------------------------------
    def check_answer(self, choice):
        if self.mode == MODE_TIMEATTACK:
            self.check_answer_timeattack(choice)
            return

        self.score_total += 1
        leveled_up = False
        is_correct = (choice == self.correct_word.correct_choice())

        if is_correct:
            self.score_correct += 1
            self.streak += 1
            if self.mode == MODE_NORMAL and self.streak >= self.STREAK_TO_LEVEL_UP:
                self.streak = 0
                self.level += 1
                leveled_up = True

            if leveled_up:
                self.message = f"正解！ レベルアップ！ Lv.{self.level} !!"
                self.message_col = pyxel.COLOR_ORANGE

                stage = (self.level - 1) // 2
                if stage > 4:
                    stage = 4
                filename = os.path.join(BASE_DIR, f"words_lv{stage + 1:02d}.csv")

                if os.path.exists(filename) and os.path.basename(filename) != self.current_wordlist:
                    new_words = load_words(filename)
                    if new_words:
                        self.words = new_words
                        self.normal_words = new_words
                        self.current_wordlist = os.path.basename(filename)
                        self.normal_wordlist_name = self.current_wordlist
                        self.word_changed = True
                        self.word_change_timer = 60
            else:
                self.message = "正解！"
                self.message_col = pyxel.COLOR_LIME
        else:
            self.streak = 0
            self.message = f"不正解… 正解は「{self.correct_word.correct_choice()}」"
            self.message_col = pyxel.COLOR_RED
            save_missed_word(self.correct_word, self.player)

        if self.mode == MODE_REVIEW:
            mastered_word = self.update_review_mastery(is_correct)
            if mastered_word:
                self.message = f"『{mastered_word}』を復習卒業！おめでとう！"
                self.message_col = pyxel.COLOR_ORANGE
            self.review_progress += 1

        self.cooldown = 45 if leveled_up else 25
        self.reset_question_keep_message()

        if self.mode == MODE_REVIEW and self.review_progress >= REVIEW_QUESTIONS:
            self.back_to_normal_after_review()
            self.reset_question()

    def update_review_mastery(self, is_correct):
        """復習モードで単語の連続正解数を記録し、既定回数に達したら
        「間違えた単語」リストから卒業させる。卒業した場合は表示用の文字列を返す。"""
        key = self.correct_word.save_key()
        mastered_label = None

        if is_correct:
            count = self.review_stats.get(key, 0) + 1
            if count >= REVIEW_MASTERY_COUNT:
                self.review_stats.pop(key, None)
                remove_missed_word(self.player, key)
                self.words = [w for w in self.words if w.save_key() != key]
                mastered_label = key[0]
            else:
                self.review_stats[key] = count
        else:
            self.review_stats[key] = 0

        save_review_stats(self.player, self.review_stats)
        return mastered_label

    def check_answer_timeattack(self, choice):
        is_correct = (choice == self.correct_word.correct_choice())

        if is_correct:
            self.ta_correct += 1
            self.ta_combo += 1
            self.ta_best_combo = max(self.ta_best_combo, self.ta_combo)

            bonus = self.ta_combo // 5
            gain = 1 + bonus
            self.ta_score += gain

            self.streak += 1
            leveled_up = False
            if self.streak >= self.STREAK_TO_LEVEL_UP:
                self.streak = 0
                self.level += 1
                leveled_up = True
                self.reload_timeattack_wordlist()

            if leveled_up:
                self.message = f"Lv.{self.level} にアップ！ +{gain}点"
                self.message_col = pyxel.COLOR_ORANGE
            elif self.ta_combo % 5 == 0:
                self.message = f"コンボ x{self.ta_combo}！ +{gain}点"
                self.message_col = pyxel.COLOR_ORANGE
            elif bonus > 0:
                self.message = f"正解！ +{gain}点（コンボ x{self.ta_combo}）"
                self.message_col = pyxel.COLOR_LIME
            else:
                self.message = "正解！"
                self.message_col = pyxel.COLOR_LIME
        else:
            self.ta_wrong += 1
            self.ta_combo = 0
            self.ta_score -= 1
            self.message = f"不正解… 正解は「{self.correct_word.correct_choice()}」"
            self.message_col = pyxel.COLOR_RED
            save_missed_word(self.correct_word, self.player)

        self.cooldown = 12
        self.reset_question_keep_message()

    def reset_question_keep_message(self):
        msg = self.message
        col = self.message_col
        self.reset_question()
        self.message = msg
        self.message_col = col

    # ------------------------------------------------------------------
    def draw(self):
        if self.state == STATE_PLAYER_SELECT:
            self.draw_player_select()
        elif self.state == STATE_START:
            self.draw_start()
        elif self.state == STATE_RESULT:
            self.draw_result()
        else:
            self.draw_play()

    def draw_start(self):
        pyxel.cls(pyxel.COLOR_PEACH)
        for x, y, col, r in self.bg_dots:
            pyxel.circ(x, y, r, col)

        pyxel.rect(0, 0, self.SCREEN_W, self.HEADER_H, pyxel.COLOR_PINK)
        pyxel.rect(0, self.HEADER_H, self.SCREEN_W, 3, pyxel.COLOR_ORANGE)
        pyxel.clip(0, 0, self.SCREEN_W, self.HEADER_H)
        self.draw_big_text(16, 8, "英単語トレーニング", pyxel.COLOR_WHITE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_PURPLE, max_width=self.SCREEN_W - 90)
        pyxel.text(16, 40, f"プレイヤー: {self.player}", pyxel.COLOR_WHITE, self.font_s)
        pyxel.clip()

        bx, by, bw, bh = self.player_switch_button_rect()
        pyxel.rect(bx, by, bw, bh, pyxel.COLOR_PURPLE)
        pyxel.rectb(bx, by, bw, bh, pyxel.COLOR_WHITE)
        pyxel.clip(bx, by, bw, bh)
        pyxel.text(bx + 4, by + 5, "人を変える", pyxel.COLOR_WHITE, self.font_s)
        pyxel.clip()

        self.draw_big_text(30, 72, "モードをえらんでね", pyxel.COLOR_PURPLE, self.font_s,
                            scale=2, outline_col=pyxel.COLOR_WHITE, max_width=self.SCREEN_W - 44)

        normal_rect, review_rect, timeattack_rect = self.start_screen_rects()
        missed_count = self.cached_missed_count

        x, y, w, h = normal_rect
        pyxel.rect(x, y, w, h, pyxel.COLOR_LIME)
        pyxel.rectb(x, y, w, h, pyxel.COLOR_WHITE)
        pyxel.clip(x, y, w, h)
        self.draw_big_text(x + 14, y + 12, "通常モード", pyxel.COLOR_PURPLE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_WHITE, max_width=w - 20)
        pyxel.clip()

        x, y, w, h = review_rect
        review_col = pyxel.COLOR_ORANGE if missed_count > 0 else pyxel.COLOR_GRAY
        pyxel.rect(x, y, w, h, review_col)
        pyxel.rectb(x, y, w, h, pyxel.COLOR_WHITE)
        pyxel.clip(x, y, w, h)
        self.draw_big_text(x + 14, y + 4, "復習モード", pyxel.COLOR_WHITE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_PURPLE, max_width=w - 20)
        pyxel.text(x + 14, y + 34, f"間違えた単語: {missed_count}問", pyxel.COLOR_WHITE, self.font_s)
        pyxel.clip()

        x, y, w, h = timeattack_rect
        pyxel.rect(x, y, w, h, pyxel.COLOR_CYAN)
        pyxel.rectb(x, y, w, h, pyxel.COLOR_WHITE)
        pyxel.clip(x, y, w, h)
        self.draw_big_text(x + 14, y + 4, "タイムアタック", pyxel.COLOR_PURPLE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_WHITE, max_width=w - 20)
        pyxel.text(x + 14, y + 34, "5分間で連続正解のコンボを狙え！", pyxel.COLOR_PURPLE, self.font_s)
        pyxel.clip()

        if self.notice:
            pyxel.rect(0, 280, self.SCREEN_W, 20, pyxel.COLOR_WHITE)
            pyxel.text(20, 286, self.notice, pyxel.COLOR_RED, self.font_s)
        else:
            pyxel.text(20, 290, "タップしてモードを選んでね", pyxel.COLOR_GRAY, self.font_s)

    # ------------------------------------------------------------------
    def draw_play(self):
        pyxel.cls(pyxel.COLOR_PEACH)
        for x, y, col, r in self.bg_dots:
            pyxel.circ(x, y, r, col)

        pyxel.rect(0, 0, self.SCREEN_W, self.HEADER_H, pyxel.COLOR_PINK)
        pyxel.rect(0, self.HEADER_H, self.SCREEN_W, 3, pyxel.COLOR_ORANGE)
        pyxel.clip(0, 0, self.SCREEN_W, self.HEADER_H)

        if self.mode == MODE_TIMEATTACK:
            header1 = f"タイムアタック  スコア {self.ta_score}"
        else:
            mode_label = "復習モード" if self.mode == MODE_REVIEW else f"Lv.{self.level}"
            header1 = f"{mode_label}  正解 {self.score_correct}/{self.score_total}"
        self.draw_big_text(10, 4, header1, pyxel.COLOR_WHITE, self.font_s,
                            scale=2, outline_col=pyxel.COLOR_PURPLE, max_width=self.SCREEN_W - 66)

        if self.mode == MODE_REVIEW:
            header2 = f"復習 {self.review_progress}/{REVIEW_QUESTIONS}問"
        elif self.mode == MODE_TIMEATTACK:
            remaining_frames = max(0, self.ta_duration_frames - (pyxel.frame_count - self.ta_start_frame))
            remaining_sec = remaining_frames // FPS
            header2 = f"残り {remaining_sec // 60}:{remaining_sec % 60:02d}"
        else:
            header2 = f"連続 {self.streak}/{self.STREAK_TO_LEVEL_UP}"
        pyxel.text(10, 36, header2, pyxel.COLOR_YELLOW, self.font_s)

        if self.mode == MODE_TIMEATTACK:
            pyxel.text(80, 36, f"コンボ x{self.ta_combo}  正{self.ta_correct} 誤{self.ta_wrong}",
                       pyxel.COLOR_YELLOW, self.font_s)
            pyxel.text(10, 48, f"Lv.{self.level}  単語帳:{self.current_wordlist}",
                       pyxel.COLOR_YELLOW, self.font_s)
        elif self.mode == MODE_REVIEW:
            streak = self.review_stats.get(self.correct_word.save_key(), 0)
            pyxel.text(10, 48, f"連続正解 {streak}/{REVIEW_MASTERY_COUNT}回で卒業",
                       pyxel.COLOR_YELLOW, self.font_s)
        else:
            pyxel.text(10, 48, f"単語帳: {self.current_wordlist}", pyxel.COLOR_YELLOW, self.font_s)

        pyxel.clip()

        bx, by, bw, bh = self.back_button_rect()
        pyxel.rect(bx, by, bw, bh, pyxel.COLOR_PURPLE)
        pyxel.rectb(bx, by, bw, bh, pyxel.COLOR_WHITE)
        pyxel.clip(bx, by, bw, bh)
        pyxel.text(bx + 4, by + 5, "戻る", pyxel.COLOR_WHITE, self.font_s)
        pyxel.clip()

        # --- 問題文（WordQuiz は英文、WordBasic は「英単語:」カード） ---
        is_quiz = isinstance(self.correct_word, WordQuiz)
        if is_quiz:
            y = self.HEADER_H + 8
            q_lines = wrap_text(self.font_s, self.correct_word.question, self.SCREEN_W - 40, max_lines=2)
            for line in q_lines:
                pyxel.text(20, y, line, pyxel.COLOR_PURPLE, self.font_s)
                y += 12
            jp_lines = wrap_text(self.font_s, self.correct_word.japanese, self.SCREEN_W - 40, max_lines=2)
            for line in jp_lines:
                pyxel.text(20, y, line, pyxel.COLOR_GRAY, self.font_s)
                y += 12
        else:
            card_y = self.HEADER_H + 8
            card_h = 26
            pyxel.rect(16, card_y, self.CHOICE_W + 8, card_h, pyxel.COLOR_LIGHT_BLUE)
            pyxel.rectb(16, card_y, self.CHOICE_W + 8, card_h, pyxel.COLOR_WHITE)
            pyxel.clip(16, card_y, self.CHOICE_W + 8, card_h)
            self.draw_big_text(24, card_y + 5, f"英単語: {self.correct_word.english}",
                                pyxel.COLOR_PURPLE, self.font_l, scale=2,
                                outline_col=pyxel.COLOR_WHITE, max_width=self.CHOICE_W - 10)
            pyxel.clip()

            y = self.HEADER_H + 38
            for line in self.example_en_lines:
                pyxel.text(20, y, line, pyxel.COLOR_PURPLE, self.font_s)
                y += 12
            if self.example_en_lines:
                y += 2
            for line in self.example_ja_lines:
                pyxel.text(20, y, line, pyxel.COLOR_GRAY, self.font_s)
                y += 12

        # --- 選択肢（マウスが乗っている項目はハイライト、色はカラフルに） ---
        hover_i = self.hovered_choice_index() if (self.cooldown == 0 and not self.word_changed) else -1
        choice_scale = 2 if self.choice_h >= 34 else 1
        for i, choice in enumerate(self.choices):
            x, yb, w, h = self.choice_rect(i)
            base_col = CHOICE_COLORS[i % len(CHOICE_COLORS)]
            if i == hover_i:
                pyxel.rect(x - 2, yb - 2, w + 4, h + 4, pyxel.COLOR_YELLOW)
            pyxel.rect(x, yb, w, h, base_col)
            pyxel.rectb(x, yb, w, h, pyxel.COLOR_WHITE)
            pyxel.clip(x, yb, w, h)
            self.draw_big_text(x + 10, yb + max(2, (h - 12 * choice_scale) // 2), choice,
                                pyxel.COLOR_PURPLE, self.font_l, scale=choice_scale,
                                outline_col=pyxel.COLOR_WHITE, max_width=w - 20)
            pyxel.clip()

        # --- 正解／不正解メッセージ（バナー風に目立たせる） ---
        pyxel.rect(0, 276, self.SCREEN_W, 18, pyxel.COLOR_WHITE)
        pyxel.clip(0, 276, self.SCREEN_W, 18)
        self.draw_big_text(10, 278, self.message, self.message_col, self.font_s,
                            scale=1, max_width=self.SCREEN_W - 20)
        pyxel.clip()
        pyxel.text(20, 300, "Qキー:終了　右上「戻る」で最初へ", pyxel.COLOR_GRAY, self.font_s)

        if self.word_changed:
            pyxel.rect(20, 120, self.SCREEN_W - 40, 80, pyxel.COLOR_ORANGE)
            pyxel.rectb(20, 120, self.SCREEN_W - 40, 80, pyxel.COLOR_WHITE)
            pyxel.clip(20, 120, self.SCREEN_W - 40, 80)
            self.draw_big_text(35, 140, "単語帳が変わったよ！",
                                pyxel.COLOR_WHITE, self.font_l, scale=2,
                                outline_col=pyxel.COLOR_PURPLE, max_width=self.SCREEN_W - 90)
            pyxel.text(35, 175, f"Now: {self.current_wordlist}", pyxel.COLOR_WHITE, self.font_s)
            pyxel.clip()

    # ------------------------------------------------------------------
    def draw_result(self):
        pyxel.cls(pyxel.COLOR_PEACH)
        for x, y, col, r in self.bg_dots:
            pyxel.circ(x, y, r, col)

        pyxel.rect(0, 0, self.SCREEN_W, self.HEADER_H, pyxel.COLOR_PINK)
        pyxel.rect(0, self.HEADER_H, self.SCREEN_W, 3, pyxel.COLOR_ORANGE)
        pyxel.clip(0, 0, self.SCREEN_W, self.HEADER_H)
        self.draw_big_text(16, 16, "タイムアタック結果", pyxel.COLOR_WHITE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_PURPLE, max_width=self.SCREEN_W - 24)
        pyxel.clip()

        y = self.HEADER_H + 10
        pyxel.text(20, y, f"プレイヤー: {self.player}", pyxel.COLOR_PURPLE, self.font_s)
        y += 16

        pyxel.rect(16, y, self.CHOICE_W + 8, 28, pyxel.COLOR_LIGHT_BLUE)
        pyxel.rectb(16, y, self.CHOICE_W + 8, 28, pyxel.COLOR_WHITE)
        pyxel.clip(16, y, self.CHOICE_W + 8, 28)
        self.draw_big_text(24, y + 5, f"スコア: {self.ta_final_score}", pyxel.COLOR_PURPLE, self.font_l,
                            scale=2, outline_col=pyxel.COLOR_WHITE, max_width=self.CHOICE_W - 10)
        pyxel.clip()
        y += 34

        pyxel.text(20, y, f"最高コンボ: x{self.ta_best_combo}　正解{self.ta_correct} 不正解{self.ta_wrong}",
                   pyxel.COLOR_PURPLE, self.font_s)
        y += 16

        if self.ta_is_new_best:
            pyxel.rect(16, y, self.CHOICE_W + 8, 26, pyxel.COLOR_YELLOW)
            pyxel.rectb(16, y, self.CHOICE_W + 8, 26, pyxel.COLOR_WHITE)
            pyxel.clip(16, y, self.CHOICE_W + 8, 26)
            self.draw_big_text(24, y + 4, "Hi-Score!!", pyxel.COLOR_RED, self.font_l,
                                scale=2, outline_col=pyxel.COLOR_WHITE, max_width=self.CHOICE_W - 10)
            pyxel.clip()
            y += 32

        pyxel.text(20, y, "ランキング TOP5", pyxel.COLOR_PURPLE, self.font_s)
        y += 14

        for i, (p, s) in enumerate(self.ranking_rows):
            is_this_entry = (p == self.player)
            col = pyxel.COLOR_ORANGE if is_this_entry else pyxel.COLOR_GRAY
            pyxel.text(20, y, f"{i + 1}. {p}  {s}点", col, self.font_s)
            y += 13
            if y > 292:
                break

        pyxel.text(20, 300, "タップしてスタート画面へ", pyxel.COLOR_GRAY, self.font_s)


WordGame()
