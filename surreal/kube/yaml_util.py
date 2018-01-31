import yaml
import jinja2
import pprint
import uuid
import contextlib
import os
import os.path as path
from io import StringIO
from easydict import EasyDict
from collections import OrderedDict


def recursive_to_dict(easy_dict):
    """
    Recursively convert back to builtin dict type
    """
    d = {}
    for k, value in easy_dict.items():
        if isinstance(value, EasyDict):
            d[k] = recursive_to_dict(value)
        elif isinstance(value, (list, tuple)):
            d[k] = type(value)(
                recursive_to_dict(v)
                if isinstance(v, EasyDict)
                else v for v in value
            )
        else:
            d[k] = value
    return d


def file_content(fpath):
    with open(path.expanduser(fpath), 'r') as fp:
        return fp.read()


class Quoted(str):
    """
    https://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data
    """
    pass

class Literal(str):
    """
    Multi-line literals
    """
    pass

def _quoted_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
yaml.add_representer(Quoted, _quoted_presenter)

def _literal_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
yaml.add_representer(Literal, _literal_presenter)

def _ordered_dict_presenter(dumper, data):
    return dumper.represent_dict(data.items())
yaml.add_representer(OrderedDict, _ordered_dict_presenter)


class YamlList(object):
    def __init__(self, data_list):
        """
        Args:
            data_list: a list of dictionaries
        """
        assert isinstance(data_list, list)
        for d in data_list:
            assert isinstance(d, dict)
        self.data_list = [EasyDict(d) for d in data_list]

    def __getitem__(self, index):
        assert isinstance(index, int)
        return self.data_list[index]

    def save(self, fpath):
        """
        Args:
            fpath: yaml path
        """
        with open(path.expanduser(fpath), 'w') as fp:
            # must convert back to normal dict; yaml serializes EasyDict object
            yaml.dump_all(
                [recursive_to_dict(d) for d in self.data_list],
                fp,
                default_flow_style=False,
            )

    def to_string(self):
        stream = StringIO()
        yaml.dump_all(
            [recursive_to_dict(d) for d in self.data_list],
            stream,
            default_flow_style=False,
            indent=2
        )
        return stream.getvalue()

    @contextlib.contextmanager
    def temp_file(self, folder='.'):
        """
        Returns:
            the temporarily generated path (uuid4)
        """
        temp_fname = 'kube-{}.yml'.format(uuid.uuid4())
        temp_fpath = path.expanduser(path.join(folder, temp_fname))
        self.save(temp_fpath)
        yield temp_fpath
        os.remove(temp_fpath)

    @classmethod
    def from_file(cls, fpath):
        with open(path.expanduser(fpath), 'r') as fp:
            return cls(list(yaml.load_all(fp)))

    @classmethod
    def from_string(cls, text):
        return cls(list(yaml.load_all(text)))

    @classmethod
    def from_template_string(cls,
                             text,
                             context=None,
                             **context_kwargs):
        """
        Render as Jinja template
        Args:
            text: template text
            context: a dict of variables to be rendered into Jinja2
            **context_kwargs: same as context
        """
        return cls.from_string(JinjaYaml(text).render(
            context=context,
            **context_kwargs
        ))

    @classmethod
    def from_template_file(cls,
                           template_path,
                           context=None,
                           **context_kwargs):
        """
        Render as Jinja template
        Args:
            template_path: yaml file with Jinja2 syntax
            context: a dict of variables to be rendered into Jinja2
            **context_kwargs: same as context
        """
        return cls.from_string(JinjaYaml.from_file(template_path).render(
            context=context,
            **context_kwargs
        ))

    def __str__(self):
        return self.to_string()


class JinjaYaml(object):
    """
    Jinja for rendering yaml
    """
    def __init__(self, text):
        self.text = text

    def render(self, context=None, **context_kwargs):
        """
        Args:
            template_path: yaml file with Jinja2 syntax
            context: a dict of variables to be rendered into Jinja2
            **context_kwargs: same as context

        Returns:
            rendered text
        """
        if context is not None:
            assert isinstance(context, dict)
            context_kwargs.update(context)
        for key, value in context_kwargs.items():
            if isinstance(value, str) and '\n' in value:
                # correctly render multiline in Yaml
                # remove the first and last single quote, change them to literal double quotes
                context_kwargs[key] = '"{}"'.format(repr(value)[1:-1])
        template = jinja2.Template(
            self.text,
            trim_blocks=True,
            lstrip_blocks=True
        )
        return template.render(context_kwargs)

    def render_file(self, out_file, context=None, **context_kwargs):
        """
        Render as Jinja template
        Args:
            template_path: yaml file with Jinja2 syntax
            context: a dict of variables to be rendered into Jinja2
            **context_kwargs: same as context
        """
        with open(path.expanduser(out_file), 'w') as fp:
            fp.write(self.render(context=context, **context_kwargs))

    @contextlib.contextmanager
    def render_temp_file(self, folder='.', context=None, **context_kwargs):
        """
        Returns:
            the temporarily generated yaml (uuid4)
        """
        temp_fname = 'jinja-{}.yml'.format(uuid.uuid4())
        temp_fpath = path.expanduser(path.join(folder, temp_fname))
        self.render_file(temp_fpath, context=context, **context_kwargs)
        yield temp_fpath
        os.remove(temp_fpath)

    @classmethod
    def from_file(cls, template_path):
        return cls(file_content(template_path))


if __name__ == '__main__':
    y = YamlList.from_template_string('shit: {{ shit  }} \n'
                                      'myseq: "{% for n in range(10) %} my{{ n }} {% endfor %}"\n'
                                      'mylist: {{lis|join("$")}}', shit='yoyo', n=7, lis=[100,99,98])

    with y.temp_file() as fname:
        os.system('cat ' +fname)
    print(y)
    print(y[0].mylist)
    print('='*40)

    y = JinjaYaml('shit: {{ shit  }} \n'
                                      'myseq: "{% for n in range(10) %} my{{ n }} {% endfor %}"\n'
                                      'mylist: {{lis|join("$")}}')
    print(y.render(shit='yoyo\ndamn\n\nlol', n=7, lis=[100,99,98]))
