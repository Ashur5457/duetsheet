# Translating Duetsheet

Duetsheet ships with six interface languages: English, Traditional Chinese (`zh-Hant`), Simplified Chinese (`zh-Hans`), Japanese (`ja`), Korean (`ko`) and Spanish (`es`). The first time you open it, it picks the language of your browser. You can switch at any time from the language menu at the top right.

The interface language only changes buttons, labels and messages. The report content (titles, text, captions) and the stored data (field names, tag ids) are never translated.

There are two ways to add a language or improve a translation.

## 1. In the page, no code needed

1. Open the language menu and choose **Add your language…**
2. Click **Download template**. You get a JSON file with every sentence of the interface in English. If you start from a language that is already translated, the current translation is filled in next to each sentence, so you only need to correct what you want to change.
3. Fill in:
   - `"_code"`: a language code, for example `fr`, `de`, `pt-BR` or `vi`
   - `"_name"`: the name of the language written in that language, for example `Français`
   - the translations. Leave a sentence empty to keep it in English.
4. Click **Load translation file** and choose your file. The page switches to your language right away.

A loaded language is kept in your browser only (other people do not see it). You can remove it again from the same dialog. Loading a file for a built-in code such as `ja` overrides only the sentences in your file; the others keep the built-in translation.

## 2. For everyone: send it to the project

Open a pull request, or attach your JSON file to a GitHub issue if you prefer not to touch the code, and we will add it.

The translations live in one block inside `duetsheet.html`:

```html
<script type="application/json" id="duetsheet-i18n">
{
"zh-Hant": {
 "_name": "...",
 "Send comment": "...",
 ...
},
"ja": { ... }
}
</script>
```

- Each language is an object whose keys are the **English text exactly as it appears in the code**, and whose values are the translation.
- `_name` is the language name shown in the menu.
- Keep placeholders such as `{n}`, `{name}` or `{a}` unchanged. They are replaced with numbers or names when the page runs. You may move them within the sentence.
- A few keys start with a context, for example `field|Text` or `timeline|Current`. They are used where the same English word needs a different translation in a different place: `Text` is the block type, while `field|Text` is the text field in the change log. If your language uses the same word in both places, copy the same translation.
- Some keys start or end with a space or punctuation, for example `" (log)"` or `"Location: "`. They are joined to other text, so keep the spacing that looks right in your language.
- To add a new built-in language, also add its code to `BUILTIN_LANGS` in the script and, if it needs its own font, to `FONT_SUFFIX` and the `:root:lang(...)` font rules in the CSS.

Then run the checker from the repository root:

```bash
python tools/check.py
```

It reports how many sentences each language has, and fails if a placeholder is missing, if a key does not exist, or if non-English text appears outside the translation block.

## For developers: adding interface text

- Write every new piece of interface text as `tr('English text')`, or `tr('Page {a} of {b}', {a: 1, b: 6})` with placeholders.
- Add the English text as a key to every language in the translation block, at least to `zh-Hant`. The Traditional Chinese table is the reference list of sentences: the **Download template** button offers exactly its keys, and `tools/check.py` fails if a `tr()` string is missing from it.
- Never put translated text into stored data. Store ids or English values and translate them when displaying.
- Translated text is always inserted as plain text (`textContent`), never as HTML, because translation files can come from anyone.
