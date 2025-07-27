import hashlib
import re

import wikitextparser as wtp


class ParseOptionTemplate:
    """Dedicates to parse "剧情选项" templates. It should have been written with
    libraries like `wikitextparser`. They can greatly simplify this parser and
    are more convenient.
    """

    def __init__(self, code: str) -> None:
        self._code = code
        self._punctuators = ['{', '}', '|', '=']
        self._is_in_template = False
        self._start = 0
        self._end = 0

    def _is_at_end(self):
        return self._end >= len(self._code)

    def _peek(self, offset: int = 0):
        return self._code[self._end + offset]

    def _advance(self):
        self._end += 1

    def _eat(self):
        char = self._peek()
        self._advance()

        return char

    def _get_param_val(self):
        while self._peek() != '=':
            self._advance()

        param_name = self._code[self._start + 1: self._end]
        # self._start + 1 is to remove | before parameter.

        self._advance()  # Skip "="
        self._start = self._end

        nested_temp_start = None
        nested_temp_end = None
        nested_temp_spans = []
        nested_temp_counter = 0
        pos = 0

        code = self._code[self._start:]
        while pos < len(code):
            char = code[pos]

            if char == '{':
                if nested_temp_start is None:
                    nested_temp_start = pos
                    pos += 2  # skip the following embrace
                    nested_temp_counter += 1
                else:
                    nested_temp_counter += 1
                    pos += 2  # skip the following embrace
            elif char == '}':
                if nested_temp_counter > 0:
                    nested_temp_counter -= 1
                    pos += 2  # skip the following embrace
                if nested_temp_counter == 0:
                    if (nested_temp_start is not None and
                            nested_temp_end is None):
                        nested_temp_end = pos
                        nested_temp_spans.append(
                            (nested_temp_start, nested_temp_end))

                        nested_temp_start = None
                        nested_temp_end = None
                    elif code[pos + 1] != '' and code[pos + 1] != '}':
                        pos += 1
                        continue
                    else:
                        break
            elif char == '|' and nested_temp_counter == 0:
                break
            else:  # for characters not punctuators
                pos += 1

        self._end += pos
        content = code[:pos]
        output = {
            'type': 'template',
            'name': param_name,
            'nested_temp_spans': nested_temp_spans,
            'value': content.strip(),
            'is_nested_temp': False
        }

        return output

    def _parse(self):
        """
        ### NOTE
        This method presumes that only the template "剧情选项"
        will be passed.
        """
        char = self._eat()

        match char:
            case space if space.isspace():
                return None
            case char if char == '|' and self._is_in_template:
                return self._get_param_val()
            case '{':
                self._is_in_template = True
                self._advance()  # skip the following embrace.
                return None
            case char if char not in self._punctuators:
                while self._peek() not in self._punctuators:
                    self._advance()
                return {
                    'type': 'template_name'
                            if self._is_in_template else 'common_string',
                    'content': self._code[self._start: self._end].strip(),
                    'is_nested_temp': False
                }
            case '}':
                return None
            case _:
                raise ValueError(f'Not supported character: {char}')

    def scan(self):
        tokens = []
        while not self._is_at_end():
            if token := self._parse():
                tokens.append(token)
            self._start = self._end
        return tokens


class Parse:
    def __init__(self, code: str) -> None:
        self.__code = self.__preprocess(code)
        self.__ignored_templates = [
            '任务',
            '面包屑',
            'JS',
            '左侧目录',
            '提示',
            '任务描述',
            '图标',
            '黑幕',
            '图片放大',
            '提示',
            '悬浮框'
        ]

    @staticmethod
    def __preprocess(code: str):
        return code.replace('<tabber>', '{{tabber|')\
                   .replace('</tabber>', '}}')\
                   .replace('|-|', '|')

    @staticmethod
    def __clean_string(string: str):
        unwanted_chars: list[str] = [
            ':',
            '<br>',
            '*',
            '----'
        ]
        escaped_chars = [re.escape(char) for char in unwanted_chars]
        pattern = '|'.join(escaped_chars) + '|<[^>]+>'

        return re.sub(pattern, '', string)

    def __sequence_string(self, string: str):
        string = string.strip()
        string = self.__clean_string(string)

        if string.find('\n') == -1:
            return string if string else None
        else:
            return [s for s in string.split('\n') if s]

    def __numeric_hash(self, text: str):
        '''
        To cope with the missing 'b' in the next method
        (see `__parse_plot_option_temp` and its comments).
        '''
        hash_bytes = hashlib.sha256(text.encode()).digest()
        hash_int = int.from_bytes(hash_bytes, byteorder='big')
        return str(hash_int)[:10]

    def __parse_plot_option_temp(self, code: str):
        expanded = []

        def traverse_nested_template(temp_dict: dict):
            has_no_nested_temp = \
                (temp_dict['type'] in ['redundant_string', 'template_name']
                 or
                 len(temp_dict['nested_temp_spans']) == 0
                 )
            if has_no_nested_temp:
                if 'value' in temp_dict:
                    if seq := self.__sequence_string(temp_dict['value']):
                        temp_dict['value'] = seq
                
                if not temp_dict['is_nested_temp']:
                    expanded.append(temp_dict)
                
                return

            value = temp_dict['value']
            nested_temp = {}
            string_with_replaced_temps = []
            slice_start = 0
            for (nested_temp_left_pos, nested_temp_right_pos) in temp_dict['nested_temp_spans']:
                string_with_replaced_temps.append(
                    value[slice_start:nested_temp_left_pos])
                slice_start = nested_temp_right_pos
                nested_temp_string = \
                    value[nested_temp_left_pos:nested_temp_right_pos]

                # 'b' is missing in the saved MD5. Re-written as the below one.
                # temp_md5 = hashlib.md5(nested_temp_string.encode()).hexdigest()[:10]
                # string_with_replaced_temps.append(temp_md5)

                temp_md5 = self.__numeric_hash(nested_temp_string)
                string_with_replaced_temps.append(f'$${temp_md5}$$')

                parser_ = ParseOptionTemplate(nested_temp_string)
                parsed = parser_.scan()
                is_plot_option_temp = \
                    any(plot_option_parsing_result['type'] == 'template_name' and
                        plot_option_parsing_result['content'] == '剧情选项'
                        for plot_option_parsing_result in parsed)
                if not is_plot_option_temp:
                    for t in wtp.parse(nested_temp_string).templates:
                        # only top-level template(s) needed
                        if t.nesting_level == 1:
                            parsed = self.__handle_temp(t)
                else:
                    for parsing_result in parsed:
                        parsing_result.update({'is_nested_temp': True})
                        traverse_nested_template(parsing_result)

                if parsed is not None:
                    nested_temp.update({temp_md5: parsed})

            string_with_replaced_temps.append(
                value[slice_start:])  # append remains of the code
            temp_dict['value'] = self.__sequence_string(
                ''.join(string_with_replaced_temps))
            temp_dict.update({'nested_temp': nested_temp})
            if not temp_dict['is_nested_temp']:
                expanded.append(temp_dict)

        parser = ParseOptionTemplate(code)
        for d in parser.scan():
            traverse_nested_template(d)

        return expanded

    def __parse(self, string: str):
        parts = []
        prev_temp_right_pos = 0
        parsed = wtp.parse(string)
        top_templates = [t for t in parsed.templates if t.nesting_level == 1]

        template: wtp.Template
        for idx, template in enumerate(top_templates):
            if idx < len(top_templates) - 1:
                # start of next top-level template
                nxt_slice_pos = top_templates[idx + 1].span[0]
            else:
                nxt_slice_pos = None

            left, t, right = (
                string[prev_temp_right_pos:template.span[0]],
                self.__handle_temp(template),
                string[template.span[1]:nxt_slice_pos] if nxt_slice_pos else string[template.span[1]:]
            )
            prev_temp_right_pos = nxt_slice_pos

            if left.strip() != '':
                # Section not followed by a template may incur the lost of content.
                # This can fix the issue.
                if seq := self.__sequence_string(left):
                    parts.append([{
                        'type': 'common_string',
                        'content': seq
                    }])

            if t is not None:
                parts.append(t)

            if right.strip() != '':
                if seq := self.__sequence_string(right):
                    parts.append([{
                        'type': 'common_string',
                        'content': seq
                    }])

        return parts

    def __handle_temp(self, template: wtp.Template):
        if template.name in self.__ignored_templates:
            return None

        match template.name.strip():
            case temp_name if temp_name in self.__ignored_templates:
                return None
            case 'tabber':
                return [arg.value for arg in template.arguments]
            case '剧情选项':
                return self.__parse_plot_option_temp(template.string)
            case '折叠':
                if content := template.get_arg('内容'):
                    content = content.string[4:]
                    if content.find('{{') != -1:
                        content = self.__parse(content)
                    else:
                        content = self.__sequence_string(content)

                    if content:
                        return [{
                            'type': 'collapse',
                            'content': content
                        }]

                return None
            case '颜色':
                color, content = template.arguments
                if color == '描述':
                    return f'$$DESCRIPTION{content}$$'
                else:
                    if seq := self.__sequence_string(content.string[1:]):
                        return [{
                            'type': 'description',
                            'content': seq
                        }]
                    return None
            case _:
                raise NotImplementedError(f'{template.name} has no parsing function.')

    def __parse_by_section(self, section: wtp.Section):
        if title := section.title:
            return [
                {
                    'type': 'section_name',
                    'content': title
                },
                self.__parse(section.contents)
            ]
        else:
            return None

    def parse(self):
        parsed_sections = []
        sections = wtp.parse(self.__code).sections

        lvl2_section = sections[1]
        deeper_sections = sections[2:]
        lines_between = lvl2_section.string.replace(
            ''.join([a.string for a in deeper_sections]).strip(), '')
        sections = deeper_sections
        if lines_between != '':
            sections = wtp.parse(lines_between).sections + sections
            # There will be just one section.

        for sec in sections:
            if parsed := self.__parse_by_section(sec):
                parsed_sections.append(parsed)

        return parsed_sections

if __name__ == '__main__':
    import parse
    from json import dump


    with open('template.txt', 'r', encoding='utf-8') as fp:
        code = fp.read()

    p = parse.Parse(code)

    with open('test_template.json', 'w', encoding='utf-8') as fp:
        dump(p.parse(), fp, ensure_ascii=False, indent=4)

