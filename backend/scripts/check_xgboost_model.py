import pickle, os
p='models/xgboost_valuation_model.pkl'
print('MODEL_PATH:',p)
print('EXISTS:', os.path.exists(p))
if os.path.exists(p):
    try:
        with open(p,'rb') as f:
            m=pickle.load(f)
        print('LOADED_TYPE:', type(m))
        print('HAS_PREDICT:', hasattr(m,'predict'))
    except Exception as e:
        print('LOAD_ERROR:', e)
else:
    print('SKIP_LOAD')
