import argparse


# set for MSR-VTT defaults
def parse_opts():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--dataset',
        type=str,
        default='msvd',
        choices=[
            'msvd',
            'msrvtt'],
        help='Dataset to use')

    parser.add_argument(
        '--model_id',
        type=str,
        help='unique identifier for model')
    parser.add_argument(
        '--results_dir',
        type=str,
        default='experiments',
        help='directory to store results')

    parser.add_argument(
        '--model_file',
        type=str,
        help='output model file')
    parser.add_argument(
        '--result_file',
        type=str,
        help='output result file')

    parser.add_argument(
        '--concepts_h5',
        type=str,
        default='sequencelabel',
        help='what concept labels to use as generated from extract_svo.py')

    parser.add_argument(
        '--train_label_h5',
        type=str,
        help='path to the h5file containing the preprocessed dataset')
    parser.add_argument(
        '--val_label_h5',
        type=str,
        help='path to the h5file containing the preprocessed dataset')
    parser.add_argument(
        '--test_label_h5',
        type=str,
        help='path to the h5file containing the preprocessed dataset')

    parser.add_argument(
        '--train_feat_h5',
        type=str,
        nargs='+',
        help='path to the h5 file containing extracted features')
    parser.add_argument(
        '--val_feat_h5',
        type=str,
        nargs='+',
        help='path to the h5 file containing extracted features')
    parser.add_argument(
        '--test_feat_h5',
        type=str,
        nargs='+',
        help='path to the h5 file containing extracted features')

    parser.add_argument(
        '--bfeat_h5', 
        type=str,
        nargs='+',
        help='path to the h5 file containing extracted features')
    parser.add_argument(
        '--fr_size_h5',
        type=str,
        help='path to the h5 file containing frame size')

    parser.add_argument(
        '--train_cocofmt_file',
        type=str,
        help='Gold captions in MSCOCO format to cal language metrics')
    parser.add_argument(
        '--val_cocofmt_file',
        type=str,
        help='Gold captions in MSCOCO format to cal language metrics')
    parser.add_argument(
        '--test_cocofmt_file',
        type=str,
        help='Gold captions in MSCOCO format to cal language metrics')

    parser.add_argument(
        '--train_bcmrscores_pkl',
        type=str,
        help='Pre-computed Cider-D metric for all captions')

    parser.add_argument(
        '--train_cached_tokens',
        type=str,
        help='Path to idx document frequencies to cal Cider on training data')

    parser.add_argument(
        '--input_features',
        default='imrc',
        type=str,
        help='i image, m motion, r region, c classification')

    # Optimization: General
    parser.add_argument(
        '--max_patience',
        type=int,
        default=50,
        help='max number of epoch to run since the minima is detected -- early stopping')
    parser.add_argument(
        '--batch_size',
        type=int,
        default=64,
        help='Video batch size (there will be x seq_per_img sentences)')
    parser.add_argument(
        '--test_batch_size',
        type=int,
        default=64,
        help='what is the batch size in number of images per batch? (there will be x seq_per_img sentences)')
    parser.add_argument(
        '--train_seq_per_img',
        type=int,
        default=20,
        help='number of captions to sample for each image during training. Done for efficiency since CNN forward pass is expensive.')
    parser.add_argument(
        '--test_seq_per_img',
        type=int,
        default=20,
        help='number of captions to sample for each image during training. Done for efficiency since CNN forward pass is expensive.')
    parser.add_argument(
        '--train_captions_per_img',
        type=int,
        default=20,
        help='number of captions to sample for each image during training. Done for efficiency since CNN forward pass is expensive.')
    parser.add_argument(
        '--test_captions_per_img',
        type=int,
        default=20,
        help='number of captions to sample for each image during training. Done for efficiency since CNN forward pass is expensive.')
    parser.add_argument(
        '--learning_rate',
        type=float,
        default=1e-4,
        help='learning rate')
    parser.add_argument(
        '--lr_update',
        default=200,
        type=int,
        help='Number of epochs to update the learning rate.')

    # Model settings
    parser.add_argument(
        '--captioner_type',
        type=str,
        default='lstm',
        choices=[
            'lstm',
            'gru',
            'rnn',
            'transformer'],
        help='type of RNN')
    parser.add_argument(
        '--captioner_size',
        type=int,
        default=512,
        help='size of the captioner in number of hidden nodes in each layer')
    parser.add_argument(
        '--captioner_layers',
        type=int,
        default=1,
        help='number of layers in the captioner')
    parser.add_argument(
        '--captioner_heads',
        type=int,
        default=1,
        help='number of heads in the captioner')
    parser.add_argument(
        '--filter_type',
        type=str,
        default='svo_original',
        choices=[
            'none',
            'tran_enc',
            'svo_original',
            'svo_transformer',
            'svo_transformer_2',
            'concept_transformer',
            'visual_encoder_only'],
        help='type of the filtering prior to captioning')
    parser.add_argument(
        '--input_encoder_size',
        type=int,
        default=512,
        help='size of the input in number of hidden nodes in each encoder layer')
    parser.add_argument(
        '--input_encoder_layers',
        type=int,
        default=0,
        help='number of layers in the input encoder')
    parser.add_argument(
        '--input_encoder_heads',
        type=int,
        default=1,
        help='number of heads in the input encoder')
    parser.add_argument(
        '--grounder_type',
        type=str,
        default='none',
        choices=[
            'none',
            'niuc',
            'nioc',
            'iuc',
            'ioc'],
        help='type of the grounding prior to captioning')
    parser.add_argument(
        '--grounder_size',
        type=int,
        default=512,
        help='size of the grounder in number of hidden nodes in each grounder layer')
    parser.add_argument(
        '--grounder_layers',
        type=int,
        default=1,
        help='number of layers in the grounder')
    parser.add_argument(
        '--grounder_heads',
        type=int,
        default=1,
        help='number of heads in the grounder decoder')
    parser.add_argument(
        '--gt_concepts_while_training',
        type=int,
        default=1,
        help='use the ground truth concepts for input into the caption generator during training')
    parser.add_argument(
        '--gt_concepts_while_testing',
        type=int,
        default=0,
        help='use the ground truth concepts for input into the caption generator during testing, useful for best case check')

    parser.add_argument(
        '--num_concepts',
        type=int,
        default=3,
        help='number of concepts (normally 3, 5)')

    parser.add_argument(
        '--att_size',
        type=int,
        default=512,
        help='size of the att in number of hidden nodes')
    parser.add_argument(
        '--num_lm_layer',
        type=int,
        default=1,
        help='size of the rnn in number of hidden nodes in each layer')
    parser.add_argument(
        '--input_encoding_size',
        type=int,
        default=512,
        help='the encoding size of each frame in the video.')
    parser.add_argument(
        '--max_epochs',
        type=int,
        default=200,
        help='max number of epochs to run for (-1 = run forever)')
    parser.add_argument(
        '--grad_clip',
        type=float,
        default=0.25,
        help='clip gradients at this value (note should be lower than usual 5 because we normalize grads by both batch and seq_length)')
    parser.add_argument(
        '--drop_prob_lm',
        type=float,
        default=0.5,
        help='strength of dropout in the Language Model RNN')

    # Optimization: for the Language Model
    parser.add_argument(
        '--optim',
        type=str,
        default='adam',
        help='what update to use? sgd|sgdmom|adagrad|adam')
    parser.add_argument(
        '--optim_alpha',
        type=float,
        default=0.8,
        help='alpha for adagrad/rmsprop/momentum/adam')
    parser.add_argument(
        '--optim_beta',
        type=float,
        default=0.999,
        help='beta used for adam')
    parser.add_argument(
        '--optim_epsilon',
        type=float,
        default=1e-8,
        help='epsilon that goes into denominator for smoothing')

    # Evaluation/Checkpointing
    parser.add_argument(
        '--save_checkpoint_from',
        type=int,
        default=1,
        help='Start saving checkpoint from this epoch')
    parser.add_argument(
        '--save_checkpoint_every',
        type=int,
        default=1,
        help='how often to save a model checkpoint in epochs?')

    parser.add_argument(
        '--use_rl',
        type=int,
        default=0,
        help='Use RL training or not')
    parser.add_argument(
        '--use_rl_after',
        type=int,
        default=0,  # 30
        help='Start RL training after this epoch')
    parser.add_argument(
        '--expand_feat',
        type=int,
        default=1,
        help='To expand features when sampling (to multiple captions)')

    parser.add_argument(
        '--start_from',
        type=str,
        default='',
        help='Load state from this file to continue training')
    parser.add_argument(
        '--language_eval',
        type=int,
        default=1,
        help='Evaluate language evaluation')
    parser.add_argument(
        '--eval_metric',
        default='CIDEr',
        choices=[
            'Loss',
            'Bleu_4',
            'METEOR',
            'ROUGE_L',
            'CIDEr',
            'MSRVTT'],
        help='Evaluation metrics')
    parser.add_argument(
        '--test_language_eval',
        type=int,
        default=1,
        help='Evaluate language evaluation')

    parser.add_argument(
        '--print_log_interval',
        type=int,
        default=20,
        help='How often do we snapshot losses, for inclusion in the progress dump? (0 = disable)')
    parser.add_argument(
        '--loglevel',
        type=str,
        default='DEBUG',
        choices=[
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'])

    # misc
    parser.add_argument(
        '--seed',
        type=int,
        default=123,
        help='random number generator seed to use')
    parser.add_argument(
        '--gpuid',
        type=int,
        default=7,
        help='which gpu to use. -1 = use CPU')
    parser.add_argument(
        '--num_chunks',
        type=int,
        default=1,
        help='1: no attention, > 1: attention with num_chunks')

    parser.add_argument(
        '--model_type',
        type=str,
        default='concat',
        choices=[
            'standard',
            'concat',
            'manet',
            ],
        help='Type of models')

    parser.add_argument(
        '--decouple',
        type=int,
        default=0,
        choices=[0,1],
        help='decouple the concept and visual feats?')

    parser.add_argument(
        '--pass_all_svo',
        type=int,
        default=0,
        choices=[0,1],
        help='Pass all s,v,o to the LSTM cap gen, or just v')

    parser.add_argument(
        '--clamp_concepts',
        type=int,
        default=1,
        choices=[0, 1],
        help='0: Use decoder output at t-1 as decoder input at t. 1: Clamp decoder output at t-1 to best word, and get this word embedding for decoder input at t.')

    parser.add_argument(
        '--beam_size',
        type=int,
        default=5,
        help='Beam search size')
    parser.add_argument(
        '--labda',
        type=float,
        default=12.0,
        help='Weights on svos over captions')

    parser.add_argument(
        '--use_ss',
        type=int,
        default=0,
        help='Use schedule sampling')
    parser.add_argument(
        '--use_ss_after',
        type=int,
        default=0,
        help='Use schedule sampling after this epoch')
    parser.add_argument(
        '--ss_max_prob',
        type=float,
        default=0.25,
        help='Use schedule sampling')
    parser.add_argument(
        '--ss_k',
        type=float,
        default=100,
        help='plot k/(k+exp(x/k)) from x=0 to 400, k=30')

    parser.add_argument(
        '--use_mixer',
        type=int,
        default=0, # 1
        help='Use schedule sampling')
    parser.add_argument(
        '--mixer_from',
        type=int,
        default=-1,
        help='If -1, then an annealing scheme will be used, based on mixer_descrease_every.\
        Initially it will set to the max_seq_length (30), and will be gradually descreased to 1.\
        If this value is set to 1 from the begininig, then the MIXER approach is not applied')
    parser.add_argument(
        '--mixer_descrease_every',
        type=int,
        default=2,
        help='Epoch interval to descrease mixing value')
    parser.add_argument(
        '--use_cst',
        type=int,
        default=0,
        help='Use cst training')
    parser.add_argument(
        '--use_cst_after',
        type=int,
        default=0,
        help='Start cst training after this epoch')
    parser.add_argument(
        '--cst_increase_every',
        type=int,
        default=5,
        help='Epoch interval to increase cst baseline')
    parser.add_argument(
        '--scb_baseline',
        type=int,
        default=1,
        help='which Self-consensus baseline (SCB) to use? 1: GT SCB, 2: Model Sample SCB')
    parser.add_argument(
        '--scb_captions',
        type=int,
        default=0,
        help='-1: annealing, otherwise using this fixed number to be the number of captions to compute SCB')
    parser.add_argument(
        '--use_eos',
        type=int,
        default=0,
        help='If 1, keep <EOS> in captions of the reference set')
    parser.add_argument(
        '--output_logp',
        type=int,
        default=0,
        help='Output average log likehood of the test and GT captions. Used for robustness analysis at test time.')
    
    
    args = parser.parse_args()
    return args
