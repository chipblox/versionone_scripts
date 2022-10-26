#!/usr/bin/env python

import os
import json
import argparse

DEFAULT_ITEM_ATTRS=['Name']
DEFAULT_EPIC_ATTRS=['Number','Category'] + DEFAULT_ITEM_ATTRS

def jsonable_convert(v1_obj, fields=None):
    jsonable_dict = {}
    item_fields = [] #['idref']
    item_fields.extend(DEFAULT_ITEM_ATTRS)
    if fields is not None and isinstance(fields, list):
        item_fields.extend(fields)

    for k in item_fields:
        v = getattr(v1_obj, k)
        if isinstance(v,list):
            jsonable_dict[k] = jsonable_convert_list(v)
        elif hasattr(v, 'idref'):
            if hasattr(v, 'Number'):
                jsonable_dict[k] = jsonable_convert(v)
            else:
                jsonable_dict[k] = v.Name    
        else:
            jsonable_dict[k] = v               

    return jsonable_dict

def jsonable_convert_list(v1_obj_list, fields=None):
    return [jsonable_convert(v1_obj, fields) for v1_obj in v1_obj_list]

def multidict(kv_iter):
    out = {}
    for k,v in kv_iter:
        values = out.setdefault(k,[])
        if v not in values: values.append(v)
    return out

def query(v1, extra_selects=[], wheres={}):
    all_selects=set(extra_selects) | set(DEFAULT_EPIC_ATTRS) | set(wheres.keys())
    results = v1.Epic.select(*all_selects)
    if wheres:
        results = results.where(**wheres)
    return results

# def validate(results, validator_func, field=None):
#     def attr(obj):
#         return getattr(obj, field) if field is not None else obj
# 
#     return [attr(r) for r in results if not validator_func(r)]


class Validator:
    def get_fields(self):
        raise NotImplementedError()

    def get_message(self):
        raise NotImplementedError()
 
    def validate(self, results, return_fields=None, return_jsonable=False):
        invalid_items = []
        for r in results:
            if not self.validate_item(r):
                returned_value = r
                if return_jsonable:
                    if isinstance(returned_value, list):
                        returned_value = jsonable_convert_list(returned_value, return_fields)
                    else:
                        returned_value = jsonable_convert(returned_value, return_fields)
                invalid_items.append(returned_value)
        
        return invalid_items

    def validate_item(self, item):
        raise NotImplementedError()

class NotEmptyValidator(Validator):
    def __init__(self, field):
        self.field = field
    
    def get_message(self):
        return str.format('{} is empty', self.field)

    def get_fields(self):
        return_set = set()
        return_set.add(self.field)
        return return_set
    
    def validate_item(self, item):
        val = None
        if hasattr(item, self.field):
            val = getattr(item, self.field)
        return val is not None and len(val) > 0
            
        
    
class KanbanStatus:
    def __init__(self, scope, name, validators):
        self.scope = scope
        self.name = name
        self.validators = validators
    
    def validate(self, v1, return_json=False):
        # Get scope & status reference
        scope_ref = v1.Scope.where(Name=self.scope).first().idref
        status_ref = v1.EpicStatus.where(Name=self.name).first().idref

        # Get extra_fields (optimization)
        extra_fields = set()
        for validator in self.validators:
            extra_fields = extra_fields | validator.get_fields()
        
        # Fetch items
        items = query(v1,
                    extra_fields,
                    dict(Scope=scope_ref,Status=status_ref))
        
        # Execute validators
        all_invalids = []
        for validator in self.validators:
            invalids = validator.validate(items, return_fields=DEFAULT_EPIC_ATTRS, return_jsonable=True)
            if invalids:
                all_invalids.append( ( validator.get_message(), invalids ) )
        
        return_invalids = multidict(all_invalids)
        if return_json:
            return_invalids = json.dumps(return_invalids)
        return return_invalids
        
        

VALIDATORS = {
    "NotEmpty": NotEmptyValidator
} 
    
def main():
    parser = argparse.ArgumentParser(description='export versionone stories.')
    parser.add_argument('--token', default=os.environ.get('VERSION_ONE_TOKEN'))
    parser.add_argument('--endpoint', default=os.environ.get('VERSION_ONE_ENDPOINT'))
    parser.add_argument('-s', '--scope', action='append', nargs='+')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--tsa_status', default=None)
    parser.add_argument('--sort', default='order')
    parser.add_argument('--output', default='text')
    args = parser.parse_args()
    headers = {}

    from v1pysdk import V1Meta

    if args.debug:
        import pdb;pdb.set_trace()

    v1 = V1Meta(instance_url=args.endpoint,
                token=args.token)


    validation_rules = [ 
        {
        'scope': '*BloxOne - Solution',
        'status': 'Funnel',
        'validations': {'NotEmpty':["Owners"]}
        # At least one owner in [solution leadership]
        # lower than WIP limit
        },
        {
        'scope': '*BloxOne - Solution',
        'status': 'Reviewing',
        'validations': {'NotEmpty':['Wsjf','Description', 'Custom_TSAStatus2']}
        # Has good description (check for default values?, has description changed?, PM/PO has been set)
        # Custom_TSAStatus2 has 
        },
        {
        'scope': 'B1Platform - ART',
        'status': 'Funnel',
        'validations': {'NotEmpty':["Owners"]}
        # At least one owner in [platform leadership]
        # lower than WIP imit
        },
        {
        'scope': 'B1Platform - ART',
        'status': 'Reviewing',
        'validations': {'NotEmpty':['Wsjf','Description', 'Custom_TSAStatus2']}
        }
    ]

    for rule in validation_rules:
        validators = []
        for validator_name, params in rule['validations'].items():
            for param in params:
                val_type = validators.append(VALIDATORS.get(validator_name)(param))
            stage = KanbanStatus(scope=rule['scope'], name=rule['status'], validators=validators)
            results = stage.validate(v1)
            output = json.dumps(dict(scope=stage.scope, status=stage.name, results=results))
            print(output)


if __name__ == '__main__':
    main()

