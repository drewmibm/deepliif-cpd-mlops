import nbformat
from nbconvert.preprocessors import ExecutePreprocessor,CellExecutionError

def run_pipeline_notebook(path_nb,save_notebook=False,return_raw=False,timeout=1200):
    """
    Run a pipeline notebook.
    
    path_nb: path to an existing notebook
    save_notebook: whether to write the executed notebook out with suffix '_out'
    return_raw: whether to return the raw result from `ep.preprocess(nb)` or the
                parsed cell output only
    """
    with open(path_nb) as f:
        nb = nbformat.read(f, as_version=4)

    ep = ExecutePreprocessor(timeout=timeout, kernel_name='python3')
    
    try:
        res = ep.preprocess(nb)
    except CellExecutionError:
        res = None
        print(f'Error executing the notebook {path_nb}')
        raise
    finally:
        if save_notebook:
            path_nb_out = path_nb.replace('.ipynb','_out.ipynb')
            with open(path_nb_out, 'w', encoding='utf-8') as f:
                nbformat.write(nb, f)
            print(f'Executed notebook written to {path_nb_out}')
        
        if return_raw:
            return res
        else:
            output, flag_error = extract_notebook_output(nb=nb)
            print('\n'.join(output))
            if flag_error:
                raise
            return extract_notebook_output(nb=nb)
        
def extract_notebook_output(path_nb=None,nb=None):
    """
    Extract output content from a jupyter notebook. Provide either path_nb or nb.
    
    path_nb: path to an existing notebook
    nb: an already loaded notebook
        example:
          import nbformat
          with open('mynb.ipynb') as f:
            nb = nbformat.read(f, as_version=4)
    """
    assert path_nb is not None or nb is not None, 'Provide either path_nb or nb.'
    
    if path_nb is not None:
        with open(path_nb) as f:
            nb = nbformat.read(f, as_version=4)
    
    l_output = []
    flag_error = False
    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            outputs = cell['outputs']
            if len(outputs) > 0:
                for output in outputs:
                    if output['output_type'] == 'stream':
                        l_output.append(output['text'])
                    elif output['output_type'] == 'execute_result':
                        if 'text/plain' in output['data'].keys():
                            l_output.append(output['data']['text/plain'])
                    elif output['output_type'] == 'error':
                        l_output.append('\n'.join(output['traceback']))
                        flag_error = True

    return l_output, flag_error
