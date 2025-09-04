import hashlib
import re

import wikitextparser as wtp


class _ParseOptionTemplate:
    """Dedicates to parse "剧情选项" templates. It should have been written with
    libraries like `wikitextparser` which can greatly simplify this parser and
    are more convenient.
    """
    def __init__(self, code: str) -> None:
        self._code = code
        self._punctuators = ['{', '}', '|', '=']
        self._is_in_template = False
        self._start = 0
        self._end = 0

    def _peek(self): # Get next character and not advance the pointer (self._end).
        return self._code[self._end]

    def _eat(self):
        char = self._peek()
        self._end += 1

        return char

    def _get_param_val(self):
        while self._peek() != '=':
            self._end += 1

        param_name = self._code[self._start + 1: self._end]
        # self._start + 1 is to remove | before parameter.
        _is_not_plot_option_temp = all((
            param_name == '剧情选项',
            param_name.find('选项') != -1,
            param_name.find('剧情') != -1
        )) # A 剧情选项 template must have one of them.
        if _is_not_plot_option_temp:
            raise ValueError(f'A "剧情选项" template excepted')

        self._end += 1  # Skip "="
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
                    if (nested_temp_start is not None and nested_temp_end is None):
                        nested_temp_end = pos
                        nested_temp_spans.append((nested_temp_start, nested_temp_end))

                        nested_temp_start = None
                        nested_temp_end = None
                    elif code[pos + 1] != '' and code[pos + 1] != '}':
                        pos += 1
                        continue
                    else: # No nested template
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
        *NOTE*: This method presumes that only the template "剧情选项"
        will be passed.
        """
        char = self._peek()
        self._end += 1
        # Get a character of input and advance the pointer (self._end)

        match char:
            case space if space.isspace():
                return None
            case char if char == '|' and self._is_in_template:
                return self._get_param_val()
            case '{':
                self._is_in_template = True
                self._end += 1  # skip the following embrace.
                return None
            case char if char not in self._punctuators:
                while self._peek() not in self._punctuators:
                    self._end += 1
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
        while not (self._end >= len(self._code)):
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
        # TODO Handle <tabber> properly.
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
        To cope with the missing 'b' in MD5 in the next method
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

                # Letter 'b' is missing in the saved MD5. Re-written as the below one.
                # temp_md5 = hashlib.md5(nested_temp_string.encode()).hexdigest()[:10]
                # string_with_replaced_temps.append(temp_md5)

                temp_md5 = self.__numeric_hash(nested_temp_string)
                string_with_replaced_temps.append(f'$${temp_md5}$$')
            
                parsed_nested = wtp.parse(nested_temp_string).templates
                for t in parsed_nested:
                    # only top-level template(s) needed
                    if t.nesting_level != 1:
                        continue

                    if t.name != '剧情选项':
                        parsed_nasted = self.__handle_temp(t)
                        # TODO Parse nested templates (if any).
                        if parsed_nasted is not None:
                            for result_parsed_nested in parsed_nasted:
                                if (isinstance(result_parsed_nested, dict) and 
                                    'is_nested_temp' in result_parsed_nested):
                                    result_parsed_nested.update({'is_nested_temp': True}) # type: ignore
                    else:
                        parser_nested = _ParseOptionTemplate(nested_temp_string)
                        parsed_nasted = parser_nested.scan()

                        for result_parsed_nested in parsed_nasted:
                            result_parsed_nested.update({'is_nested_temp': True})
                            traverse_nested_template(result_parsed_nested)

                    if parsed_nasted is not None:
                        nested_temp.update({temp_md5: parsed_nasted})

            string_with_replaced_temps.append(value[slice_start:])  # append remains of the code
            temp_dict['value'] = self.__sequence_string(''.join(string_with_replaced_temps))
            temp_dict.update({'nested_temp': nested_temp})
            if not temp_dict['is_nested_temp']:
                expanded.append(temp_dict)

        parser = _ParseOptionTemplate(code)
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

            left, temp, right = (
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

            if temp is not None:
                parts.append(temp)

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
                    return [{
                            'type': 'description',
                            'content': f'$$DESCRIPTION{content}$$'
                        }]
                else:
                    if seq := self.__sequence_string(content.string[1:]):
                        return [{
                            'type': 'description',
                            'content': seq
                        }]
                    return None
            case '角色对话':
                args = template.arguments
                name = args[1].string[1:] # Skip heading "|"
                msg_type = args[2].string[1:]
                content = args[3].string[1:]

                if msg_type == '文本':
                    msg_text = f'{name}：{content}'
                elif msg_type == '表情':
                    msg_text = f'{name}：……'
                elif msg_type == '图片':
                    msg_text = f'{name}：……'
                else:
                    raise ValueError(f'Message type not supported.')
                
                return [{
                        'type': 'common_string',
                        'content': msg_text
                    }]
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
    # scripts\handle_bwiki_code\test_files\test_code_with_msg_tabber_sr.txt
    with open(r'scripts\handle_bwiki_code\test_files\test_code_with_msg_tabber_sr.txt', 'r', encoding='utf-8') as fp:
        code = fp.read()

    p = Parse(code)

    from json import dump
    with open('test.json', 'w', encoding='utf-8') as fp:
        dump(p.parse(), fp, ensure_ascii=False, indent=4)
