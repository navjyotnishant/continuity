# str.split keeps empty fields
`'1,,2'.split(',')` returns `['1', '', '2']`, so the tokenizer must skip empty strings.
