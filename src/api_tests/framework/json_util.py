"""JSON utilities for Devo Apps automation."""

import json
import os


class ParseableJson:
    """A class for parsing, and comparing Json objects."""

    def __init__(self, base_json, ignore_list=None):
        """Create and walk the json object to enumerate all the nodes.

        Args:
            base_json: a json object that will be parsed.
            ignore_list: A list of keys that should be ignored when comparing json objects.
        """

        if ignore_list is None:
            ignore_list = []
        self.base_json = base_json
        self.ignore_list = ignore_list
        self.comparison_json = None
        self.comparison_dict = dict()
        self.base_dict = dict()
        current_path = ""
        self.WalkJsonNode(self.base_json, current_path)

    def WalkJsonNode(self, node_data, current_path):
        """iterate through elements within a json object, and process the end nodes

        Args:
            node_data: A list object that may contain nested lists or dictionaries
            current_path: The path in the json object to this node.
        """

        if isinstance(node_data, list):
            current_path += " [ "
            for list_element in node_data:
                self.WalkJsonNode(list_element, current_path)
        elif isinstance(node_data, dict):
            for dict_key in list(node_data.keys()):
                if dict_key not in self.ignore_list:
                    new_path = current_path + dict_key + " : "
                    self.WalkJsonNode(node_data[dict_key], new_path)
        else:
            self.ProcessNode(current_path + str(node_data) + "\n")

    def ProcessNode(self, node_value):
        """create/increment the count for the end node in a dictionary.

        When we first initialize, the comparison object is not set, so our mode will be to build
        the base dictionary.  When we call the compareJson method, the comparison object is set.
        When the comparison object is present, we build the comparison dictionary.
        For each node, if the key for the node is not present, we add it, and set the count to 1.
        If the key is already present, we increment the count.

        Args:
            node_value: A string representing the node that we want to process.
        """

        if self.comparison_json:
            self.comparison_dict[node_value] = self.comparison_dict.get(node_value, 0) + 1
        else:
            self.base_dict[node_value] = self.base_dict.get(node_value, 0) + 1

    def CompareJson(self, comparison_json):
        """Compare a second comparison json object with the base json object.

        Args:
            comparison_json: A json object that we want to compare with this json object.
        Returns:
            comparison_dict: This is the count of nodes in the comparison json object.
        """

        self.comparison_json = comparison_json
        current_path = ""
        self.WalkJsonNode(self.comparison_json, current_path)
        return self.comparison_dict


class JsonUtil:
    """A Utility Class for few JSON related operations"""

    @staticmethod
    def UpdateJson(json_file, value_dict, update_file=False):
        """Update the values from a JSON File or JSON serialized String

        Args:
            json_file: JSON File absolute path or JSON string data to update (string)
            value_dict: A Dict of values to update JSON (dict)
            update_file: If need to update the existing json file with new values(bool)

        Returns:
            data: json serialized string (str)
        """

        if os.path.exists(json_file):
            with open(json_file) as input_fp:
                data = json.load(input_fp)
        else:
            data = json.loads(json_file)
        for value in value_dict:
            if isinstance(value_dict[value], int):
                update_value = f"data{value}={value_dict[value]}"
            elif isinstance(value_dict[value], list):
                update_value = f"data{value}={value_dict[value]}"
            else:
                update_value = f'data{value}="{value_dict[value]}"'
            exec(update_value)
        if update_file:
            with open(json_file, "w") as output_fp:
                json.dump(data, output_fp)
        return json.dumps(data)

    def GetValueForKeyInDict(self, input_dict, key_val):
        """This method will return the value for specific key in a dictionary

        Args:
            input_dict: Input dictionary for which value needs to be replaced (dict)
            key_val: Key to be specified for which the value needs to be changed. For specific
                     scores, the key_val should be like
                     'enrichment.rec1_score_activity.rec1_score_score' (str)

        Returns:
            input_dict: Value of the specified key from the input_dict specified. Else will
                        return None, if not found. (str/list/dict)

        """
        if isinstance(input_dict, dict):
            for k, v in input_dict.items():
                if key_val.find(".") > 0 and k == key_val.split(".")[0]:
                    for str1 in key_val.split("."):
                        input_dict = input_dict.get(str1)
                    return input_dict
                elif key_val.find(".") == -1 and k == key_val:
                    return input_dict[k]
                else:
                    self.GetValueForKeyInDict(v, key_val)

        elif isinstance(input_dict, list):
            for val in input_dict:
                self.GetValueForKeyInDict(val, key_val)

    def GetAlertsDictList(self, input_dict, base_key="events", key_list=None, sort_field="timeStamp", sort_field1=None):
        """This method gets the list of dictionary, with values for specified keys from the mongo
        alert json.

        Args:
            input_dict: input dictionary, in which the value for specified key to be found (dict)
            base_key: The key name under which keys under key_list will be searched. (str)
            key_list: List of keys, for which the values are fetched from json (list)
                      For nested dict, the key can be specified as
                      'enrichment.rec1_score_activity.rec1_score_score'
            sort_field: One of keys from the key_list to be used for sorting (str).
                        To be specified if sort_field1 is being used.
            sort_field1: Another sort key to be specified. The output list<dict> will be sorted
                         using fields specified in sort_field & sort_field1 (str)

        Returns:
            sorted_list: Sorted list of dictionaries, if sort_field is specified.
                         Each dictionary contains values for key_list for each of the
                         events in the json.
        """

        if key_list is None:
            key_list = ["timeStamp"]

        list_dict = []
        if isinstance(input_dict, list | tuple):
            for data in input_dict:
                if base_key is not None:
                    data = self.GetValueForKeyInDict(data, base_key)

                if isinstance(data, list | tuple):
                    for values in data:
                        dict1 = dict()
                        for st in key_list:
                            dict1[st] = self.GetValueForKeyInDict(values, st)
                        list_dict.append(dict1)
                else:
                    dict1 = dict()
                    for st in key_list:
                        dict1[st] = self.GetValueForKeyInDict(data, st)
                    list_dict.append(dict1)
        else:
            if base_key is not None:
                data = self.GetValueForKeyInDict(input_dict, base_key)
            else:
                data = input_dict

            dict1 = dict()
            for st in key_list:
                dict1[st] = self.GetValueForKeyInDict(data, st)
            list_dict.append(dict1)

        if sort_field is None:
            return list_dict

        if sort_field1 is not None:
            sorted_list = sorted(list_dict, key=lambda k: (k[sort_field], k[sort_field1]))
        else:
            sorted_list = sorted(list_dict, key=lambda k: k[sort_field])
        return sorted_list
