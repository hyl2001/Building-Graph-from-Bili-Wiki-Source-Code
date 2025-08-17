'''### Utility

It contains: \n
`cyan_char`\n
`green_char`\n
'''

def cyan_char(string: str):
    return f'\033[96m{string}\033[0m'

def green_char(string: str):
    return f'\033[32m{string}\033[0m'
