#AUTOGENERATED! DO NOT EDIT! File to edit: dev/40_tabular_core.ipynb (unless otherwise specified).

__all__ = ['Tabular', 'TabularPandas', 'TabularProc', 'Categorify', 'Normalize', 'FillStrategy', 'FillMissing',
           'ReadTabBatch', 'TabDataLoader']

#Cell
from ..torch_basics import *
from ..test import *
from ..core import *
from ..data.all import *
from ..notebook.showdoc import show_doc

#Cell
pd.set_option('mode.chained_assignment','raise')

#Cell
class Tabular(CollBase):
    "A `DataFrame` wrapper that knows which cols are cont/cat/y, and returns rows in `__getitem__`"
    def __init__(self, df, procs=None, cat_names=None, cont_names=None, y_names=None, is_y_cat=True,
                 splits=None, split=None, setup=True):
        if splits is not None:
            df = df.iloc[sum(splits, [])]
            if split is None: split = len(splits[0])
        super().__init__(df.copy())
        store_attr(self, 'y_names,is_y_cat,split')
        self.cat_names,self.cont_names,self.procs = L(cat_names),L(cont_names),Pipeline(procs)
        self.cat_y  = None if not is_y_cat else y_names
        self.cont_y = None if     is_y_cat else y_names
        if setup: self.procs.setup(self)

    def new(self, df):
        return self.__class__(df, self.procs, self.cat_names, self.cont_names, self.y_names, is_y_cat=self.is_y_cat,
                              split=self.split, setup=False)

    def copy(self):
        self.items = self.items.copy()
        return self

    def __getattr__(self,k): return delegate_attr(self, k, 'items')
    def show(self, max_n=10, **kwargs): display_df(self.all_cols[:max_n])
    def process(self): self.procs(self)

    @property
    def iloc(self): return _TabIloc(self)
    @property
    def targ(self): return self.items[self.y_names]
    @property
    def all_cont_names(self): return self.cont_names + self.cont_y
    @property
    def all_cat_names (self): return self.cat_names  + self.cat_y
    @property
    def all_col_names (self): return self.all_cont_names + self.all_cat_names

#Cell
class TabularPandas(Tabular):
    def transform(self, cols, f): self[cols] = self[cols].transform(f)

#Cell
def _add_prop(cls, nm):
    prop = property(lambda o: o[list(getattr(o,nm+'_names'))])
    setattr(cls, nm+'s', prop)
    def _f(o,v): o[getattr(o,nm+'_names')] = v
    setattr(cls, nm+'s', prop.setter(_f))

_add_prop(Tabular, 'cat')
_add_prop(Tabular, 'all_cat')
_add_prop(Tabular, 'cont')
_add_prop(Tabular, 'all_cont')
_add_prop(Tabular, 'all_col')

#Cell
class TabularProc(InplaceTransform):
    "Base class to write a non-lazy tabular processor for dataframes"
    def setup(self, items=None):
        super().setup(items)
        # Procs are called as soon as data is available
        return self(items)

#Cell
class Categorify(TabularProc):
    "Transform the categorical variables to that type."
    order = 1
    def setups(self, to):
        self.classes = {n:CategoryMap(to.iloc[:to.split,n], add_na=True) for n in to.all_cat_names}

    def _apply_cats (self, c): return c.cat.codes+1 if is_categorical_dtype(c) else c.map(self[c.name].o2i)
    def _decode_cats(self, c): return c.map(dict(enumerate(self[c.name].items)))
    def encodes(self, to): to.transform(to.all_cat_names, self._apply_cats)
    def decodes(self, to): to.transform(to.all_cat_names, self._decode_cats)
    def __getitem__(self,k): return self.classes[k]

#Cell
class Normalize(TabularProc):
    "Normalize the continuous variables."
    order = 2
    def setups(self, to):
        df = to.iloc[:to.split, to.cont_names]
        self.means,self.stds = df.mean(),df.std(ddof=0)+1e-7

    def encodes(self, to): to.conts = (to.conts-self.means) / self.stds
    def decodes(self, to): to.conts = (to.conts*self.stds ) + self.means

#Cell
class FillStrategy:
    "Namespace containing the various filling strategies."
    def median  (c,fill): return c.median()
    def constant(c,fill): return fill
    def mode    (c,fill): return c.dropna().value_counts().idxmax()

#Cell
class FillMissing(TabularProc):
    "Fill the missing values in continuous columns."
    def __init__(self, fill_strategy=FillStrategy.median, add_col=True, fill_vals=None):
        if fill_vals is None: fill_vals = defaultdict(int)
        store_attr(self, 'fill_strategy,add_col,fill_vals')

    def setups(self, to):
        df = to.iloc[:to.split, to.cont_names].items
        self.na_dict = {n:self.fill_strategy(df[n], self.fill_vals[n])
                        for n in pd.isnull(to.conts).any().keys()}

    def encodes(self, to):
        missing = pd.isnull(to.conts)
        for n in missing.any().keys():
            assert n in self.na_dict, f"nan values in `{n}` but not in setup training set"
            to[n].fillna(self.na_dict[n], inplace=True)
            if self.add_col:
                to.loc[:,n+'_na'] = missing[n]
                if n+'_na' not in to.cat_names: to.cat_names.append(n+'_na')

#Cell
class ReadTabBatch(ItemTransform):
    def __init__(self, to): self.to = to
    def encodes(self, to): return (tensor(to.cats).long(),tensor(to.conts).float()), tensor(to.targ).long()

    def decodes(self, o):
        (cats,conts),targs = to_np(o)
        vals = np.concatenate([cats,conts,targs[:,None]], axis=1)
        df = pd.DataFrame(vals, columns=self.to.cat_names+self.to.cont_names+self.to.y_names)
        to = self.to.new(df)
        to = self.to.procs.decode(to)
        return to

#Cell
@delegates()
class TabDataLoader(TfmdDL):
    do_item = noops
    def __init__(self, dataset, bs=16, shuffle=False, after_batch=None, num_workers=0, **kwargs):
        after_batch = L(after_batch)+ReadTabBatch(dataset.items)
        super().__init__(dataset, bs=bs, shuffle=shuffle, after_batch=after_batch, num_workers=num_workers, **kwargs)

    def create_batch(self, b): return self.dataset.items.iloc[b]