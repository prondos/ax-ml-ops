import os
import re
import numpy as np
import pandas as pd

from axent.column_transformer import ColumnTransformer
from axent.type_transformer import TypeTransformer

import mlflow
import optuna
from optuna.integration.mlflow import MLflowCallback

from typing import List
from sklearn.impute import KNNImputer
from sklearn.preprocessing import FunctionTransformer, MinMaxScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.ensemble import RandomForestClassifier


class PipelineUtils:

    def add_dummies(df, columns: List[str], drop_first=True, pass_nan=True):
        new_columns = []
        for c in columns:
            dummies = pd.get_dummies(df[c], prefix=f'cat_{c}', drop_first=drop_first)
            new_columns += list(dummies.columns)
            df[list(dummies.columns)] = dummies
            if pass_nan:
                df.loc[(df[c].isnull()),list(dummies.columns)] = np.nan
        return df


class CustomPipelineUtils:
    
    def add_split_columns(df):
        df[['PassengerId_Group','PassengerId_Number']] = df['PassengerId'].str.split('_', expand=True)
        df[['Cabin_Deck','Cabin_Num','Cabin_Side']] = df['Cabin'].str.split('/', expand=True)
        df[['Name_First','Name_Last']] = df['Name'].str.split(' ', expand=True)
        return df

    def fillna_insights(df):
        # Sleepers and passengers under 13 do not spend money
        for c in ['RoomService', 'FoodCourt', 'ShoppingMall', 'Spa', 'VRDeck']:
            df.loc[(df['CryoSleep']==True) | (df['Age']<13), c] = 0.0
        # No VIPs from Earth
        df.loc[df['HomePlanet']=='Earth', 'VIP'] = False
        return df
                
    def log_scale(df):
        cols = ['RoomService', 'FoodCourt', 'ShoppingMall', 'Spa', 'VRDeck']
        for c in cols:
            df[c] = np.log(df[c]+1.0)
        return df

    def bin_columns(df):
        age_bins = [-1,12,18,25,30,50,800]
        df['bin_Age'] = pd.cut(df['Age'],bins=age_bins)
        dummies = pd.get_dummies(df['bin_Age'], prefix=f'cat_bin_Age')
        df[list(dummies.columns)[:-1]] = dummies[list(dummies.columns)[:-1]]
        return df
    
    def add_summary_columns(df):
        # df['agr_Sum_Expenses'] = df['RoomService'] + df['FoodCourt'] + df['ShoppingMall'] + df['Spa'] + df['VRDeck']
        # df['agr_Count_Services'] = (df[['RoomService', 'FoodCourt', 'ShoppingMall', 'Spa', 'VRDeck']]>0).T.sum().T
        df['agr_Count_PassengerId_Group_Name_Last'] = df.groupby(['PassengerId_Group','Name_Last']).transform('count')['PassengerId'].fillna(0.0)
        # df['agr_Count_Cabin_Deck'] = df.groupby(['Cabin_Deck']).transform('count')['PassengerId']
        df['agr_Count_Cabin_Num'] = df.groupby(['Cabin_Num']).transform('count')['PassengerId'].fillna(0.0)
        df['agr_Count_Cabin_Side'] = df.groupby(['Cabin_Side']).transform('count')['PassengerId'].fillna(0.0)
        df['agr_Name_Last_Count'] = df.groupby('Name_Last').transform('count')[['PassengerId']].fillna(0.0)
        df['agr_Name_First_Count'] = df.groupby('Name_First').transform('count')[['PassengerId']].fillna(0.0)
        return df

cat_cols = ['HomePlanet','CryoSleep','Destination','VIP','Cabin_Deck','Cabin_Side','PassengerId_Number']
num_cols = ['Age','RoomService', 'FoodCourt', 'ShoppingMall', 'Spa', 'VRDeck','Cabin_Num','PassengerId_Group']

def load_and_transform_data():
    df_train = pd.read_csv(os.path.dirname(__file__)+'/train.csv')
    df_train['train'] = 1

    df_test = pd.read_csv(os.path.dirname(__file__)+'/test.csv')
    df_test['train'] = 0

    df = pd.concat([df_test, df_train], ignore_index=True)

    pipeline = Pipeline(steps=[
        ('split', FunctionTransformer(CustomPipelineUtils.add_split_columns)),
        ('fillna_insights', FunctionTransformer(CustomPipelineUtils.fillna_insights)),
        ('astype_num', ColumnTransformer(TypeTransformer('float64'), columns=num_cols)),
        ('log_scale', FunctionTransformer(CustomPipelineUtils.log_scale)),
        ('astype_cat', ColumnTransformer(TypeTransformer('category'), columns=cat_cols)),
        ('add_dummies', FunctionTransformer(PipelineUtils.add_dummies, kw_args={'columns':cat_cols})),
        ('impute', ColumnTransformer(KNNImputer(), columns=num_cols+[re.compile('^cat_.*')])),
        ('bin_columns', FunctionTransformer(CustomPipelineUtils.bin_columns)),
        ('add_summary_columns', FunctionTransformer(CustomPipelineUtils.add_summary_columns)),
        ('scale_num',  ColumnTransformer(MinMaxScaler(), columns=num_cols)),
        ('scale_agr',  ColumnTransformer(MinMaxScaler(), columns=[re.compile('^agr_.*')]))
    ])

    pipeline.fit_transform(df)
    
    return df[df['train']==1], df[df['train']==0].copy()


def get_xy_cols(df):
    X_col = []
    X_col += num_cols
    X_col += [cc for cc in df.columns if cc.startswith('cat_')]
    X_col += [cc for cc in df.columns if cc.startswith('agr_')]
    X_col = [ c for c in X_col if c not in ['Age','Cabin_Num'] ]
    y_col = 'Transported'
    
    return X_col, y_col


def get_xy(df):
    X_col, y_col = get_xy_cols(df)
    X = df[X_col].to_numpy()
    if y_col in df.columns:
        y = df[y_col].astype('int').to_numpy()
    else:
        y = None
    return X, y


if __name__ == '__main__':
    mlflc = MLflowCallback(
        metric_name="accuracy",
    )

    df_train, df_test = load_and_transform_data()
    X_train, y_train = get_xy(df_train)
    X_cols, y_col = get_xy_cols(df_train)

    @mlflc.track_in_mlflow()
    def objective(trial):
        params = {
            'bootstrap': trial.suggest_categorical("bootstrap", [True, False]),
            'max_depth': trial.suggest_int("max_depth", 10, 100, step = 10),
            'max_features': trial.suggest_categorical("max_features", ['auto', 'sqrt']),
            'min_samples_leaf': trial.suggest_int("min_samples_leaf", 1, 12),
            'min_samples_split': trial.suggest_int("min_samples_split", 2, 12),
            "n_estimators": trial.suggest_int("n_estimators", 5, 2000, log = True),
            "random_state": 7
        }
        model = RandomForestClassifier(**params)

        kf = StratifiedKFold(n_splits = 5, shuffle = True, random_state = 7)
        scores = cross_validate(model, X_train, y_train, cv = kf, scoring = "accuracy", n_jobs = -1, return_train_score=True)
        
        mlflow.log_metric("cv_train_min_score", scores["train_score"].min())
        mlflow.log_metric("cv_train_mean_score", scores["train_score"].mean())
        mlflow.log_metric("cv_train_max", scores["train_score"].max())

        mlflow.log_metric("cv_test_min_score", scores["test_score"].min())
        mlflow.log_metric("cv_test_mean_score", scores["test_score"].mean())
        mlflow.log_metric("cv_test_max_score", scores["test_score"].max())

        # fit and log model
        model.fit(X_train, y_train)
        mlflow.log_metric("train_score", model.score(X_train, y_train))
        mlflow.sklearn.log_model(model, 'model')

        return scores["test_score"].mean()
    
    study = optuna.create_study(
        study_name=os.path.dirname(__file__).split(os.sep)[-1]+'-RandomForestClassifier',
        load_if_exists = True,
        direction = "maximize",
        storage=f'postgresql+psycopg2://optuna:{os.environ.get("DB_OPTUNA_PASS")}@db/optuna'
    )
    study.optimize(objective, n_trials=10, callbacks=[mlflc])