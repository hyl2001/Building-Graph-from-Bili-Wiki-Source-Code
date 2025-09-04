import networkx as nx
import re
import hashlib
import random

from copy import deepcopy
from typing import Literal


class GraphBuilder:
    def __init__(self, 
                 parsed_bwiki_template,
                 player_name: Literal['旅行者', '开拓者'],
                 *,
                 is_clps_igned: bool = True):
        '''
        Parameters
        ----------
        parsed_bwiki_template: dict
            It takes a dictionary parsed from Bilibili Wikipedia Template.
        player_name: str
            It must be one of "旅行者" or "开拓者". It is used to tag talk seteneces 
            witout name explicitly marked at the start of the sentence.
        is_clps_igned, optional
            By default True. It determines whether ignore `折叠` (collapse) template. 
            When False, collapse tamplate will be added into the graph. It should be
            True, because we do not need it in the light of experiment purpose.
        
        Raises
        ------
        ValueError
            For details, refer to exception raised.
        '''
        random.seed() # Initialize the random number generator.

        self.__parsed_bwiki_template = parsed_bwiki_template
        self.__is_clps_igned = is_clps_igned

        if player_name not in ['旅行者', '开拓者']:
            raise ValueError(f'The player name must be either "旅行者" or "开拓者"; not "{player_name}".')
        self.__player_name = player_name

        self.__speaker_content_matcher = re.compile(r'^(?P<speaker>[^:：]+?)[:：](?P<content>.*)$', re.DOTALL)
        self.__temp_hash_matcher = re.compile(r'\${2}[0-9]{10}\${2}', re.DOTALL)

    def __get_speaker_name_and_content(self, string: str):
        if string.strip() == '':
            return None, None, None
        
        # TODO Infer speaker name marked by "？？？".
        match = self.__speaker_content_matcher.match(string)
        if match:
            speaker = match.group('speaker').strip()
            content = match.group('content').strip()
        else:
            speaker = self.__player_name  # If speaker not found, use "旅行者" or "开拓者" as default.
            content = string
        
        content += f'_{random.randint(1000, 9999)}'

        # Random integer is added, considering that the potentially same speaker and talk text.
        temp_hash = hashlib.md5(string.encode() + bytes(random.randint(1000, 9999))).hexdigest()[:10]

        return temp_hash, speaker, content

    def __convert_str_seq_into_node_list(self, str_seq:list[str], node_type: list[str]):
        speaker_content_pairs = map(self.__get_speaker_name_and_content, str_seq)

        return {
            md5: {'speaker': speaker, 'content': content, 'node_type': node_type}
            for (md5, speaker, content), node_type in zip(speaker_content_pairs, node_type)
            if all((md5, speaker, content))
        }

    @staticmethod
    def __find_option_plot_pair(temp_parts:list[dict]):
        pair = {}

        for idx, part in enumerate(temp_parts):
            name: str = part['name']
            if name.find('选项') != -1:
                if name in pair:
                    raise ValueError('Redundant "选项" found.')
                
                pair[name] = {
                    'plot': None,
                    'plot_pos': None,
                    'option_pos': idx
                }
            elif name.find('剧情') != -1:
                if name in pair:
                    raise ValueError('Redundant "剧情" found.')

                plot_idx = int(name[-1].strip())
                option_of_plot = f'选项{plot_idx}'
                if option_of_plot in pair:
                    if pair[option_of_plot]['plot'] is None:
                        pair[option_of_plot]['plot'] = name
                        pair[option_of_plot]['plot_pos'] = idx
                    else:
                        raise ValueError('Existing "剧情" found.')
                else:
                    raise ValueError('No pairing "选项" found.')
            else:
                raise ValueError(f'The passed ({name}) is neither "剧情" nor "选项".')

        return pair
    
    def __build_plot_option_graph(self, 
                                  plot_option_template: list[dict],
                                  graph: nx.DiGraph | None = None,
                                  prev_node_names: list[str] | None = None,
                                  branch_name: str = 'None') -> dict:
        if prev_node_names is None:
            prev_node_names: list[str] = ['START']

        if graph is None:
            graph = nx.DiGraph()
            graph.add_node(prev_node_names[0])

        if not (plot_option_template[0]['type'] == 'template_name' and plot_option_template[0]['content'] == '剧情选项'):
            return self.__handle_component(plot_option_template)
        pair = self.__find_option_plot_pair(plot_option_template[1:])

        options_to_be_connected = {}
        for option_name, option_info in pair.items():
            option = plot_option_template[option_info['option_pos'] + 1]
        
            o_md5, o_speaker, o_content = self.__get_speaker_name_and_content(option['value'])
            if all((o_md5, o_speaker, o_content)):
                graph.add_node(
                    o_md5,
                    speaker = o_speaker,
                    content = f'{o_content}',
                    node_type = f'option{option_name[-1]}',
                    branch_name = branch_name
                )
                graph.add_edges_from(
                    zip(prev_node_names, [o_md5] * len(prev_node_names))
                )
                options_to_be_connected[option_name] = o_md5

        for option_name, option_info in pair.items():
            if option_info['plot_pos'] is None:
                continue

            paired_plot = plot_option_template[option_info['plot_pos'] + 1]
            paired_plot_name = paired_plot['name']
            paired_plot_value = paired_plot['value']
            if isinstance(paired_plot_value, str):
                paired_plot_value = [paired_plot_value]

            prev_node_names = [options_to_be_connected[option_name]]
            value: str
            for value in paired_plot_value:
                if self.__temp_hash_matcher.match(value) is not None:
                    temp_hash = value.replace('$', '')

                    prev_node_names = \
                        self.__build_plot_option_graph(
                            paired_plot['nested_temp'][temp_hash], 
                            graph, 
                            prev_node_names,
                            branch_name=str(random.randint(10000, 99999)))['end'] #type:ignore
                else:
                    p_md5, p_speaker, p_content = self.__get_speaker_name_and_content(value)
                    print(p_md5)

                    if all((p_md5, p_speaker, p_content)):
                        graph.add_node(
                            p_md5,
                            speaker = p_speaker,
                            content = f'{p_content}',
                            node_type = f'plot{paired_plot_name[-1]}',
                            branch_name = branch_name
                        )
                        graph.add_edges_from(
                            zip(prev_node_names, [p_md5] * len(prev_node_names))
                        )
                        prev_node_names = [p_md5]
        
        node_attr_and_degree = \
            zip(nx.get_node_attributes(graph, 'branch_name').items(), list(graph.out_degree)[1:])
        end = \
            [node 
            for (node, at_branch), (_, degree) in  node_attr_and_degree
            if at_branch == branch_name and degree == 0]
        # This return is for building plot option graph only.
        return {
            'graph': graph,
            'start': 'START',
            'end': end,
        }
    
    def __wrapped_build_plot_option_graph(self, components: list, is_followed_by_lines: bool):
        graph: nx.DiGraph = self.__build_plot_option_graph(components)['graph']
        leaf_nodes = [n for (n, degree) in graph.out_degree if degree == 0]

        if is_followed_by_lines:
            graph.add_node('END')
            graph.add_edges_from([(node, 'END') for node in leaf_nodes])

            return {
                'graph': graph,
                'start': 'START',
                'end': 'END'
            }
        else:
            return {
                'graph': graph,
                'start': 'START',
                'end': leaf_nodes
            }
    
    def __str_lst_to_node_lst(self, string_lst: list[str], node_type: str):
        nodes = self.__convert_str_seq_into_node_list(string_lst, [node_type] * len(string_lst))
        graph = nx.DiGraph()
        graph.add_nodes_from(nodes)
        
        hash_list = list(nodes.keys())
        origins = deepcopy(hash_list)
        origins.pop(-1)
        destinations = deepcopy(hash_list)
        destinations.pop(0)
        graph.add_edges_from(zip(origins, destinations))

        return {
            'graph': graph,
            'start': hash_list[0],
            'end': hash_list[-1]
        }
    
    def __handle_component(self, components: list, *, is_followed_by_other_lines: bool = True):
        """
        Note: this method is not well named. The `is_followed_by_other_lines`
        is for building plot option graph only.
        """
        if not components:
            return None
        
        # Act as a standard return format. Values of this dict will be replaced later and then return.
        return_dict = {
            'graph': None,
            'start': None,
            'end': None
        }

        if components[0]['type'] == 'common_string':
            return self.__str_lst_to_node_lst(components[0]['content'], 'common_string')
        elif components[0]['type'] == 'template_name':
            graph_built = self.__wrapped_build_plot_option_graph(components, is_followed_by_other_lines)
            if graph_built:
                return graph_built # consistent with standard return format
            else:
                return return_dict # All values are None.
        elif components[0]['type'] == 'collapse':
            if self.__is_clps_igned:
                return None
    
            content = components[0]['content']
            
            if isinstance(content, str):
                nodes = self.__convert_str_seq_into_node_list([components[0]['content']], ['collapse'])
                graph = nx.DiGraph()
                graph.add_nodes_from(nodes)

                hash_list = list(nodes.keys())
                return_dict['graph'] = graph # type: ignore
                return_dict['start'] = hash_list[0] # type: ignore
                return_dict['end'] = hash_list[-1] # type: ignore

                return return_dict
            elif isinstance(content, list):
                # The collapse may contain other templates.
                for c in components[0]['content']:
                    if isinstance(c, str): # Content is list
                        return self.__str_lst_to_node_lst(components[0]['content'], 'collapse')
                    elif c[0]['type'] == 'common_string': # Content is a template of commom_string
                        components_from_commom_str = [
                            {
                                "type": "collapse",
                                "content": c[0]['content']
                            }
                        ]
                        return self.__handle_component(components_from_commom_str)
                    else: # Content is others.
                        return self.__handle_component(components)
        elif components[0]['type'] == 'description':
            nodes = self.__convert_str_seq_into_node_list(components[0]['content'], ['description'])
            graph = nx.DiGraph()
            graph.add_nodes_from(nodes)
            
            hash_list = list(nodes.keys())
            return_dict['graph'] = graph # type: ignore
            return_dict['start'] = hash_list[0] # type: ignore
            return_dict['end'] = hash_list[-1] # type: ignore
            
            return return_dict
        else:
            raise NotImplementedError(f'You need to assign a method to handle the "{components[0]['type']}".')

    def build(self) -> list[nx.DiGraph]:
        '''Build plot graph.

        Returns
        -------
            A list encompassing `networkx.DiGraph`.
        '''

        graphs = []
        for section in self.__parsed_bwiki_template:
            G = nx.DiGraph()

            section_name = section[0]['content'] # type: ignore
            if section_name == '任务剧情':
                continue

            G.add_node(section_name, section_name = section_name)

            prev_node: str = section_name
            for sec_components in section[1:]:
                for component_idx, component in enumerate(sec_components):
                    if component_idx < len(sec_components):
                        graph_dict = self.__handle_component(component, is_followed_by_other_lines=True)
                    elif component_idx == len(sec_components):
                        graph_dict = self.__handle_component(component, is_followed_by_other_lines=False)
    
                    if graph_dict is not None:
                        new_G = nx.union(G, graph_dict['graph'], rename=('', ''))
                        # union() can preserve nodes' MD5 but may raise error in some cases.
                        # disjoint_union() can fix this issue but can not preserve the MD5.
                        # FIXME this issue should be fixed.

                        if isinstance(prev_node, list):
                            new_G.add_edges_from([(n, graph_dict['start']) for n in prev_node])
                        elif isinstance(prev_node, str):
                            new_G.add_edges_from([(prev_node, graph_dict['start'])])
                        
                        G = new_G
                        prev_node = graph_dict['end']
            
            graphs.append(G)
        return graphs
