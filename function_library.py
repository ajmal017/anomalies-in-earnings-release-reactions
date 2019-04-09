# required packages
import pandas as pd
import numpy as np
import quandl
from datetime import datetime, timedelta
import json
import matplotlib.pyplot as plt


from dateutil.parser import parse
from datetime import datetime
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score, KFold, GridSearchCV
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import log_loss, precision_score, confusion_matrix, precision_recall_curve
from sklearn.metrics import roc_auc_score, f1_score, make_scorer, recall_score, average_precision_score

from sklearn.utils.multiclass import unique_labels
from sklearn.utils.fixes import signature
from sklearn.preprocessing import OneHotEncoder, LabelEncoder




# function categories:
# 1) pre-processing & data partitioning
# 2) model fitting & prediction
# 2) 

# pre-processing & data partitioning functions
# helper functions

def _create_feature_df_index(df):
    """HELPER to create a new Index for extracting columns coded with a trailing 'F' from a dataframe"""
    
    old_columns = list(df.columns)
    new_columns = []
    
    for col in old_columns:
        if col[-1] == 'F':
            new_columns.append(col)
        
    new_columns.insert(0, 'unique_earnings_code')
    ind_obj = pd.Index(new_columns)
    
    return ind_obj


def _clean_feature_bind(surp_df, feature_df, retained_columns):
    """HELPER to create a tidied up df from a surp_df and feature_df, based on an Index object of cols to retain."""
    
    bound_df = pd.merge(surp_df, feature_df[retained_columns], on='unique_earnings_code')
    
    return bound_df


def _tidyfy_surp_df(df):
    """HELPER to clean up Surp dataframes prior to join"""
    new_cols = ['ticker_symbol',
                 'co_name',
                 'unique_earnings_code',
                 'factset_sector_num',
                 'factset_ind_num',
                 'calendar_qtr',
                 'fiscal_qtr',
                 'adtv_prev_month',
                 'report_date',
                 'eps_est',
                 'eps_actual',
                 'surp_amt',
                 'rtn_t+3',
                 'mkt_t+3_rtn',
                 'rel_t+3_rtn',
                 'num_ests_qtr_end',
                 't-7_high_est',
                 't-7_low_est',
                 'est_spread',
                 'spread_adj_surp']
    
    tidy_df = df[new_cols]
    tidy_df = tidy_df.drop_duplicates()
    
    return tidy_df

def _transform_dates(df, col_name):
    """HELPER to convert date columns to a sortable format"""
    dates = list(df[str(col_name)])
    new_dates = []

    for d in dates:
        dt = datetime.strptime(d, '%m/%d/%Y')
        reformatted = str(dt)
        reformatted = reformatted[:10]
        new_dates.append(reformatted)
        
    df[str(col_name)] = new_dates

def _oos_partition(filename):
    """HELPER to create out-of-sample partition of 3Q18 data."""
    
    # read file in as a df and drop unwanted column
    data = pd.read_csv('data/'+str(filename)+'.csv', low_memory=False)
    data.drop(columns='Unnamed: 0', inplace=True)
    
    # reformat dates and sort by dates, ascending
    _transform_dates(data, 'report_date')
    data.sort_values(by=['report_date'], inplace=True)
    
    # set index to unique_earnings_code
    data.set_index('unique_earnings_code', inplace=True)
    
    # partition 3q18 data to test set
    test_partition = data[data.index.str.endswith('3Q18')]
    test_partition.to_csv('data/oos_data_partition.csv')
    
    # create y_oos array
    y_oos = test_partition.targets.values
    
    # create X_oos array
    features = test_partition.columns.str.endswith('F')
    X_oos = test_partition.values[:,features]
    
    # remove test_partition from data df
    data = data[data.index.str.endswith('3Q18') == False]
    
    # create y_train and X_train arrays
    y = data.targets.values
    r = data['rel_t+3_rtn']
    X = data.values[:,features]
    
     
    return X, X_oos, y, y_oos, r

###################################################################################################

# script functions

def write_merged_frames(surp_lst, features_lst):
    """Create combined dataframes from two lists of dataframe names: surp & features"""
    
    combined_df_lst = []
    
    for s_df, f_df in zip(surp_lst, features_lst):
        #create quarter tag
        tag = s_df[-8:]

        # read surp df
        surp_df = pd.read_csv('data/'+s_df)
        tidy_surp_df = _tidyfy_surp_df(surp_df)
        # read feature df
        feature_df = pd.read_csv('data/'+f_df)

        # create list of columns to retain
        retained_cols = _create_feature_df_index(feature_df)

        # create combined df
        combined_df = _clean_feature_bind(tidy_surp_df, feature_df, retained_cols)
        

        # write combined_df to a csv file and store in data folder
        combined_df.to_csv('data/combined_'+tag, index=False)
        
        # record df written to a list
        combined_df_lst.append('combined_'+tag)
    
    return combined_df_lst


def stack_frames(sequence):
    """Concatenate combined dataframes and perform some basic data cleaning
    OUTPUT: writes combined_full_set.csv to data folder
    """
    sequence = sequence.copy()
    
    # concatenate dataframes
    combined_full = pd.concat([pd.read_csv(f'data/{file}', low_memory=False) for file in sequence])
    
    # drop empty rows
    combined_full = combined_full.drop_duplicates()
    
    # convert excel error codes to NaNs
    combined_full['rtn_t+3'] = combined_full['rtn_t+3'].apply(pd.to_numeric, args=('coerce',))
    combined_full['est_spread'] = combined_full['est_spread'].apply(pd.to_numeric, args=('coerce',))
    
    # drop rows with missing values in ticker_symbol column and NaNs in rtn_t+3 column
    combined_full = combined_full.dropna(subset=['ticker_symbol', 'rtn_t+3'])
    
    # add very small number to zero values in est_spread column to avoid division by zero
    combined_full['est_spread'] = combined_full['est_spread'].apply(pd.to_numeric, args=('coerce',))
    combined_full['est_spread'] = combined_full['est_spread'].apply(lambda x: x+0.0025 if x==0 else x)
    
    combined_full['spread_adj_surp'] = combined_full['spread_adj_surp'].apply(pd.to_numeric, args=('coerce',))
    combined_full = combined_full.dropna(subset=['spread_adj_surp'])
    
    combined_full.to_csv('data/combined_full_set.csv')
    
    return 


def create_labels(filename):
    """Creates target labels for the data set.
    INPUT: csv filename, as text
    OUTPUT: Creates primary labels based on threshold values of +/- 5% for the rel_t+3_rtn and a
    minimum spread_adj_surp of +/- 0.25 and adds them to the existing data set, writing
    them into the csv provided in column named 'targets'. Also creates alernative labels based on 
    thresholds of +/- 7.5% for the rel_t+3_rtn and a minimum spread_adj_surp of +/- 0.50 and writes
    them into column named 'extreme_targets'.    
    """
    
    # empty container for labels
    labels = []
    
    # load data from file
    data = pd.read_csv('data/'+str(filename)+'.csv', low_memory=False)
    
    # pull out key columns and convert to lists
    event_rtn = list(data['rel_t+3_rtn'])
    event_react = list(data['spread_adj_surp'])
    
       
    # create labels based on conditions
    labels = []

    for rtn, react in (zip(event_rtn, event_react)):
        if (rtn <= -5) and (react >= 0.25):
            labels.append(1)
        #elif (rtn >= 5) and (react <= -0.25):
            #labels.append(2)
        else:
            labels.append(0)
            
    # create alternative extreme targets
    xtrm_tgts = []
    
    for rtn, react in (zip(event_rtn, event_react)):
        if (rtn <= -7.5) and (react >= 0.50):
            xtrm_tgts.append(1)
        #elif (rtn >= 7.5) and (react <= -0.50):
            #xtrm_tgts.append(2)
        else:
            xtrm_tgts.append(0)
       
    # add classification targets to combined dataframe
    data.insert(loc=21, column='targets', value=labels)
    data.insert(loc=22, column='extreme_targets', value=xtrm_tgts)
    
    # drop Unnamed column
    data.drop(columns='Unnamed: 0', inplace=True)
     
    # overwrite passed file with updated df
    data.to_csv('data/'+str(filename)+'.csv')
    
    
    return


def clean_features(filename):
    """Cleans features of filename passed to function as a string.
       * Eliminates rows with excessive missing values.
       * Fills in individual missing values in columns based on industry group average for quarter.
       * Removes rows for stocks with fewer than 4 analyst estimates for a given quarter.
       OUTPUT: Writes combined_clean.csv to data folder.
    """
    
    
    # load data from file
    data = pd.read_csv('data/'+str(filename)+'.csv', low_memory=False)
    
    # eliminate observations with excessive missing values
    bad_rows = data.iloc[:,22:].isnull().sum(axis=1) > 4
    data = data[bad_rows == False]
    
    # replace missing column values with qtr averages for industry groups
    temp = data.groupby(['calendar_qtr','factset_ind_num']).transform(lambda data: data.fillna(data.mean()))

    for col in temp:
        data[col] = temp[col]
        
    # scrub any remaining missing values by dropping observations
    bad_rows = data.iloc[:,22:].isnull().sum(axis=1) > 0
    data = data[bad_rows == False]
    
    # remove observations with fewer than 4 analyst estimates for the quarter
    data = data[data['num_ests_qtr_end'] > 3]
    
    
    # drop Unnamed column
    data.drop(columns='Unnamed: 0', inplace=True)    
    
    # write output to a new file
    data.to_csv('data/combined_clean.csv')    
        
    return

    
def encode_sectors(filename):
    """Encodes factset_sector_num as binary categorical columns and writes them to the csv file
    with 'trailing F' notation."""
    data = pd.read_csv('data/'+str(filename)+'.csv', low_memory=False)
    data.drop(columns='Unnamed: 0', inplace=True)
    
    enc = OneHotEncoder(handle_unknown='ignore', sparse=False)
    sectors = data.factset_sector_num.values
    sectors = sectors.reshape(-1, 1)
    encoded_cols = enc.fit_transform(sectors)
    feature_labels = list(enc.get_feature_names())
    feature_names = []
    
    for item in feature_labels:
        tagged_name = item+'_F'
        feature_names.append(tagged_name)
    
    temp = pd.DataFrame(encoded_cols, columns=feature_names)
    data = pd.concat([data, temp], axis=1)
    # write combined_df to a csv file and store in data folder
    data.to_csv('data/'+str(filename)+'.csv')
    
    return

def prepare_partitions(filename, test_slice=0.25, rand_seed=1970):
    """Partitions 3Q18 data for out of sample validation and creates train-test split on remainder. 
            * Writes 3Q18 df to a file in the data folder: oos_data_partition.csv
            * Creates a train-test split on remaining data
            * Returns X_train, X_test, X_oos, y_train, y_test, y_oos
            
        test_slice defaults to 0.25, but can be assigned by keyword
        rand_seed defaults to 1970, but can be assigned by keyword
    """
    
    X, X_oos, y, y_oos, r = _oos_partition(filename)
    
    X_train, X_test, y_train, y_test, r_train, r_test = train_test_split(X,y, r,
                                                                                test_size=test_slice,
                                                                                random_state=rand_seed)
    
    return X_train, X_test, y_train, y_test, r_train, r_test

# end pre-processing & data partitioning section
###################################################################################################












def create_hard_classes(prob_array, threshold):
    """Helper function to create hard classifications based on a probability array and a given threshold"""
    hard_classes = []
    for row in prob_array:
        if row[1] >= threshold:
            hard_classes.append(1)
        else:
            hard_classes.append(0)
    return hard_classes






# quantcha API functions


# create a helper function for getting a measure from the quantcha / quandl API

def get_vol_measure(ticker, date, measure='Hv90'):
    """Retrieves a value from the Quantcha Historical and Implied Volatility API for a given stock and date.
    
    INPUTS: 'Ticker', 'YYYY-MM-DD', and measure name.
    For reference, measure names are contained in the dictionary: vol_col_names
        
    OUPUT: A float
    """
    
    measure_value = (quandl.get('VOL/'+ticker,
                           start_date=date,
                           end_date=date, 
                           column_index=vol_col_names.get(measure)))
                
    return float(measure_value.values)


# create a generalized measure delta function

def measure_delta(ticker, date, look_back_days, measure='Hv90'):
    """Provides a relative comparison for a given stock ticker and date, based on an arbitrary look_back_window,
    for any of 64 data itmes from the Quantcha Historical and Implied Volatility API.
    
    INPUTS: 'Ticker', 'YYYY-MM-DD', lookback days (as integer), and measure name.
    For reference, measure names are contained in the dictionary: vol_col_names
    ***NOTE: For best results, utilize a lookback window that is a multiple of 7 days from the given date.
    
    OUPUT: A float, based on the forumla: <measure at date> / <measure at date - lookback days>
    """
    
    date = datetime.strptime(date, '%Y-%m-%d')
    
    lookback_date = date - timedelta(days=int(look_back_days))
        
    date = str(date)
    date = date[0:10]
    
    lookback_date = str(lookback_date)
    lookback_date = lookback_date[0:10]
    
      
    curr_vol = (quandl.get('VOL/'+ticker,
                           start_date=date,
                           end_date=date, 
                           column_index=vol_col_names.get(measure)))
                
    
    prior_vol = (quandl.get('VOL/'+ticker,
                            start_date=lookback_date,
                            end_date=lookback_date,
                            column_index=vol_col_names.get(measure)))
      
    output = curr_vol.values / prior_vol.values
    return float(output)
