
import argparse
import os
import csv
import json
import h5py
import cv2
import spacy
import sys
import nltk
from nltk import WordNetLemmatizer
from nltk.stem import PorterStemmer
import numpy as np
import glob
import pickle as pkl
from autocorrect import Speller

sys.path.append('coco-caption')
from pycocoevalcap.bleu.bleu import Bleu
from pycocoevalcap.meteor.meteor import Meteor
from pycocoevalcap.rouge.rouge import Rouge
from pycocoevalcap.cider.cider import Cider
from pycocoevalcap.spice.spice import Spice

# todo add more stats including missed words, nouns, verbs, also svo stats
# to get 'en_core_web_sm' run:
# python -m spacy download en_core_web_sm

# wordlemmatizer = WordNetLemmatizer()
# nlp = spacy.load('en_core_web_sm')
# ps = PorterStemmer()
# sp = Speller()

#
# if os.path.exists(os.path.join('glove6b', 'glove.6B.300d.pkl')):
# 	glove = pickle.load(open(os.path.join('glove6b', 'glove.6B.300d.pkl'), 'rb'))
# else:
# 	glove = dict()
# 	with open(os.path.join('glove6b', 'glove.6B.300d.txt'), 'r') as f:
# 		lines = f.readlines()
# 		for line in lines:
# 			word_split = line.rstrip().split(' ')
# 			word = word_split[0]
#
# 			d = word_split[1:]
# 			d = [float(e) for e in d]
# 			glove[word] = d
# 	pickle.dump(glove, open(os.path.join('glove6b', 'glove.6B.300d.pkl'), 'wb'))


def calc_scores(scorers, gt, pr):
	"""
	Calculate Scores for the metrics in scorers, with groundtruth (gt) and predictions (pr)
	"""
	scores_dict = dict()
	for scorer, method in scorers:
		# print('computing %s score...' % (scorer.method()))
		score, scores = scorer.compute_score(gt, pr)
		if type(method) == list:
			for sc, scs, m in zip(score, scores, method):
				# print("%s: %0.3f" % (m, sc))
				scores_dict[m] = sc
		else:
			# print("%s: %0.3f" % (method, score))
			scores_dict[method] = score

	return scores_dict


def scorer_names_list(scorers):
	"""
	Get list of names of the scorers - basically extracts the BLEUs into the rest of the list
	"""
	scorer_names = list()
	for s in scorers:
		if type(s[1]) == list:
			scorer_names += s[1]
		else:
			scorer_names += [s[1]]
	return scorer_names


def gt_v_gt(gt_json, out_dir, scorers):
	"""
	Run human evaluation, comparing the groundtruth captions with one another

	Will generate:
		- gt_summary.csv : per sample average metric results
		- gt_detatiled.csv : more detailed summary with errors per caption per sample, plus worst, best and avg scores
		- gt_avg_scores.npy : a numpy array version of the gt_summary.csv
		- gt_scores.json : a json version of the gt_detatiled.csv
	"""

	os.makedirs(out_dir, exist_ok=True)

	scorer_names = scorer_names_list(scorers)

	gt_sum_csv_file = open(os.path.join(out_dir, 'gt_summary.csv'), mode='w')
	gt_sum_csv_writer = csv.writer(gt_sum_csv_file, delimiter=',')
	gt_sum_csv_writer.writerow(['VID'] + scorer_names + [''] + scorer_names + [''] + scorer_names)
	gt_sum_csv_writer.writerow([])

	gt_csv_file = open(os.path.join(out_dir, 'gt_detailed.csv'), mode='w')
	gt_csv_writer = csv.writer(gt_csv_file, delimiter=',')
	gt_csv_writer.writerow(['VID', 'CAP #', 'CAP'] + scorer_names)

	all_scores = list()
	all_scores_dict = dict()
	for cnt, gt_item in enumerate(gt_json):

		gt_csv_writer.writerow([])
		gt_csv_writer.writerow([])

		vid = gt_item['video_id']
		gt_caps = gt_item['captions']

		all_scores_dict[vid] = {'groundtruths': list()}

		# human evaluation best, worst, avg gt v gt
		human_scores = dict()
		for i, gt_cap in enumerate(gt_caps):
			gt = {vid: [gt_caps[j] for j in range(len(gt_caps)) if j != i]}
			pr = {vid: [gt_cap]}

			scores_dict = calc_scores(scorers, gt, pr)
			for k, v in scores_dict.items():
				if k not in human_scores:
					human_scores[k] = list()
				human_scores[k].append(v)

			scores_list = list()
			for scorer_name in scorer_names:
				scores_list.append(scores_dict[scorer_name])
			if i == 0:
				gt_csv_writer.writerow([vid, i+1, gt_cap] + scores_list)
			else:
				gt_csv_writer.writerow(['', i+1, gt_cap] + scores_list)

			all_scores_dict[vid]['groundtruths'].append({'id': i, 'caption': gt_cap, 'scores': scores_dict})

		avg_human_scores = dict()
		best_human_scores = dict()
		worst_human_scores = dict()
		for k, v in human_scores.items():
			avg_human_scores[k] = sum(v)/len(v)
			best_human_scores[k] = max(v)
			worst_human_scores[k] = min(v)

		gt_csv_writer.writerow([])

		summary = [vid]
		scores_list = list()
		for scorer_name in scorer_names:
			scores_list.append(avg_human_scores[scorer_name])
		gt_csv_writer.writerow(['', '', 'AVERAGE'] + scores_list)
		summary += scores_list + ['']
		all_scores.append(scores_list)
		all_scores_dict[vid]['scores'] = avg_human_scores

		scores_list = list()
		for scorer_name in scorer_names:
			scores_list.append(best_human_scores[scorer_name])
		gt_csv_writer.writerow(['', '', 'BEST'] + scores_list)
		summary += scores_list + ['']

		scores_list = list()
		for scorer_name in scorer_names:
			scores_list.append(worst_human_scores[scorer_name])
		gt_csv_writer.writerow(['', '', 'WORST'] + scores_list)
		summary += scores_list

		gt_sum_csv_writer.writerow(summary)

		print("------------------------------- %d / %d -------------------------------" % (cnt+1, len(gt_json)))

	np.save(os.path.join(out_dir, 'gt_avg_scores.npy'), np.array(all_scores))
	gt_sum_csv_writer.writerow(['AVERAGE'] + list(np.mean(np.array(all_scores), axis=0)))
	gt_csv_file.close()
	gt_sum_csv_file.close()

	with open(os.path.join(out_dir, 'gt_scores.json'), 'w') as f:
		json.dump(all_scores_dict, f)


def pr_v_gt(gt_json, pr_json, out_dir, scorers):
	"""
	Run model evaluation, comparing the model prediction with the groundtruth captions

	Will generate:
		- pr_summary.csv : per sample average metric results
		- pr_detatiled.csv : more detailed summary with errors per caption per sample
		- pr_avg_scores.npy : a numpy array version of the pr_summary.csv
		- pr_scores.json : a json version of the pr_detatiled.csv
	"""

	os.makedirs(out_dir, exist_ok=True)

	scorer_names = scorer_names_list(scorers)

	pr_sum_csv_file = open(os.path.join(out_dir, 'pr_summary.csv'), mode='w')
	pr_sum_csv_writer = csv.writer(pr_sum_csv_file, delimiter=',')
	pr_sum_csv_writer.writerow(['VID'] + scorer_names)

	pr_csv_file = open(os.path.join(out_dir, 'pr_detailed.csv'), mode='w')
	pr_csv_writer = csv.writer(pr_csv_file, delimiter=',')
	pr_csv_writer.writerow(['VID', 'PR CAP', 'GT CAP'] + scorer_names)

	all_scores = list()
	all_scores_dict = dict()
	for cnt, (gt_item, pr_item) in enumerate(zip(gt_json, pr_json['predictions'])):
		assert gt_item['video_id'] == pr_item['image_id']
		pr_csv_writer.writerow([])

		vid = gt_item['video_id']
		gt_caps = gt_item['captions']
		pred_caps = [pr_item['caption']]
		all_scores_dict[vid] = {'predictions': pred_caps, 'groundtruths': list()}

		pred_scores = dict()
		for i, gt_cap in enumerate(gt_caps):
			gt = {vid: [gt_cap]}
			pr = {vid: pred_caps}

			scores_dict = calc_scores(scorers, gt, pr)
			for k, v in scores_dict.items():
				if k not in pred_scores:
					pred_scores[k] = list()
				pred_scores[k].append(v)

			scores_list = list()
			for scorer_name in scorer_names:
				scores_list.append(scores_dict[scorer_name])
			if i == 0:
				pr_csv_writer.writerow([vid, pred_caps[0], gt_cap] + scores_list)
			else:
				pr_csv_writer.writerow(['', '', gt_cap] + scores_list)
			all_scores_dict[vid]['groundtruths'].append({'id': i, 'caption': gt_cap, 'scores': scores_dict})

		avg_pred_scores = dict()
		for k, v in pred_scores.items():
			avg_pred_scores[k] = sum(v)/len(v)

		scores_list = list()
		for scorer_name in scorer_names:
			scores_list.append(avg_pred_scores[scorer_name])
		pr_csv_writer.writerow(['', '', 'AVERAGE A'] + scores_list)

		gt = {vid: gt_caps}
		pr = {vid: pred_caps}
		avg_pred_scores_b = calc_scores(scorers, gt, pr)
		scores_list = list()
		for scorer_name in scorer_names:
			scores_list.append(avg_pred_scores_b[scorer_name])
		pr_csv_writer.writerow(['', '', 'AVERAGE B'] + scores_list)
		pr_sum_csv_writer.writerow([vid] + scores_list)
		all_scores_dict[vid]['scores'] = avg_pred_scores_b
		all_scores.append(scores_list)

		print("------------------------------- %d / %d -------------------------------" % (cnt+1, len(gt_json)))

	np.save(os.path.join(out_dir, 'pr_avg_scores.npy'), np.array(all_scores))
	pr_sum_csv_writer.writerow(['AVERAGE'] + list(np.mean(np.array(all_scores), axis=0)))
	pr_csv_file.close()
	pr_sum_csv_file.close()

	with open(os.path.join(out_dir, 'pr_scores.json'), 'w') as f:
		json.dump(all_scores_dict, f)


def make_summary_video(dataset, out_dir, clip_dir, pr_json, gt_json, pr_det_json, gt_det_json, boxes_h5):

	pr_svos = dict()
	pr_atts = dict()
	for v in pr_json['predictions']:
		pr_svos[v['image_id']] = v['svo']
		pr_atts[v['image_id']] = v['box_att']

	# build avgs dicts and difference list
	pr_avgs = dict()
	gt_avgs = dict()
	diffs = list()
	for vid in pr_det_json.keys():
		pred_scores = pr_det_json[vid]['scores']
		pr_avgs[vid] = sum(list(pred_scores.values()))/len(pred_scores)

		gt_scores = gt_det_json[vid]['scores']
		gt_avgs[vid] = sum(list(gt_scores.values()))/len(gt_scores)

		diffs.append([vid, gt_avgs[vid]-pr_avgs[vid]])

	# sort biggest diffs (worst vids) first
	diffs.sort(key=lambda x: x[1], reverse=True)

	# make video
	out = cv2.VideoWriter(os.path.join(out_dir, dataset + '_summary.mp4'), cv2.VideoWriter_fourcc('m', 'p', '4', 'v'), 30, (1920, 1080))

	for vi, (vid, diff) in enumerate(diffs):
		print("%d / %d" % (vi, len(diffs)))

		boxes = boxes_h5[vid]

		# organise gt caps
		gt_caps = pr_det_json[vid]['groundtruths']
		gt_caps_human = gt_det_json[vid]['groundtruths']

		gt_caps_list = list()
		for i in range(len(gt_caps)):
			assert gt_caps[i]['id'] == gt_caps_human[i]['id']
			assert gt_caps[i]['caption'] == gt_caps_human[i]['caption']
			pr_avg = sum(list(gt_caps[i]['scores'].values()))/len(gt_caps[i]['scores'])
			gt_avg = sum(list(gt_caps_human[i]['scores'].values()))/len(gt_caps_human[i]['scores'])
			gt_caps_list.append([gt_caps[i]['caption'], pr_avg, gt_avg, gt_avg-pr_avg])

		gt_caps_list.sort(key=lambda x: x[3], reverse=True)

		# load video
		if dataset in ['msrvtt']:
			cap = cv2.VideoCapture(os.path.join(clip_dir, 'video'+vid+'.mp4'))
			total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
		if dataset in ['msvd']:
			with open(os.path.join('datasets', 'msvd', 'youtube_id_to_video_mapping.pkl'), 'rb') as f:
				mapping = pkl.load(f)
			cap = cv2.VideoCapture(os.path.join(clip_dir, mapping['vid'+vid]+'.avi'))
			total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
		else:
			return NotImplementedError

		if not cap.isOpened():
			print("Error opening video stream or file")

		# write on frame
		frame = np.ones((1080, 1920, 3), dtype=np.uint8)*20
		pred_cap = pr_det_json[vid]['predictions'][0]

		pred_scores = pr_det_json[vid]['scores']
		pred_scores_avg = sum(list(pr_det_json[vid]['scores'].values()))/len(pr_det_json[vid]['scores'])
		gt_scores = gt_det_json[vid]['scores']
		gt_scores_avg = sum(list(gt_det_json[vid]['scores'].values()))/len(gt_det_json[vid]['scores'])

		font_scale = 0.5
		pad = 22

		cv2.putText(frame, "VIDEO : %s" % vid, (1600, 20), 0, font_scale*1.2, (255, 255, 255))

		# prediction cap
		cv2.putText(frame, "PRED AVG", (1600, 520), 0, font_scale, (150, 150, 150))
		cv2.putText(frame, "GT AVG", (1700, 520), 0, font_scale, (150, 150, 150))
		cv2.putText(frame, "DIFF AVG", (1800, 520), 0, font_scale, (150, 150, 150))
		cv2.putText(frame, pred_cap, (20, 520+pad), 0, font_scale*1.5, (0, 255, 0))
		cv2.putText(frame, "%.4f" % pred_scores_avg, (1600, 520+pad), 0, font_scale, (0, 255, 0))
		cv2.putText(frame, "%.4f" % gt_scores_avg, (1700, 520+pad), 0, font_scale, (0, 255, 0))
		cv2.putText(frame, "%.2f" % (gt_scores_avg-pred_scores_avg), (1800, 520+pad), 0, font_scale, (0, 255, 0))

		# ground truth caps
		cv2.putText(frame, "PRED VS", (1600, 550+pad), 0, font_scale, (150, 150, 150))
		cv2.putText(frame, "GT VS", (1700, 550+pad), 0, font_scale, (150, 150, 150))
		cv2.putText(frame, "DIFF", (1800, 550+pad), 0, font_scale, (150, 150, 150))
		for i, gt_cap in enumerate(gt_caps_list):
			if dataset == 'msrvtt' or i < 10:
				cv2.putText(frame, gt_cap[0], (20, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.4f" % gt_cap[1], (1600, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.4f" % gt_cap[2], (1700, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.2f" % gt_cap[3], (1800, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
			elif i > len(gt_caps_list) - 10:
				cv2.putText(frame, gt_cap[0], (20, 550+pad+(1+i-(len(gt_caps_list) - 20))*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.4f" % gt_cap[1], (1600, 550+pad+(1+i-(len(gt_caps_list) - 20))*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.4f" % gt_cap[2], (1700, 550+pad+(1+i-(len(gt_caps_list) - 20))*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "%.2f" % gt_cap[3], (1800, 550+pad+(1+i-(len(gt_caps_list) - 20))*pad), 0, font_scale, (255, 255, 0))
			elif i == 10:
				cv2.putText(frame, '......', (20, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "......", (1600, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "......", (1700, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))
				cv2.putText(frame, "......", (1800, 550+pad+(1+i)*pad), 0, font_scale, (255, 255, 0))

		# metric results
		for i, (k, v) in enumerate(pred_scores.items()):
			cv2.putText(frame, "%s" % k, (1500, 320+i*pad), 0, font_scale, (150, 150, 150))
			cv2.putText(frame, "%.4f" % v, (1600, 320+i*pad), 0, font_scale, (0, 255, 0))
			cv2.putText(frame, "%.4f" % gt_scores[k], (1700, 320+i*pad), 0, font_scale, (255, 255, 0))

		# prediction svo
		cv2.putText(frame, "SVO", (1500, 50), 0, font_scale*1.2, (150, 150, 150))
		cv2.putText(frame, "%s" % pr_svos[int(vid)], (1600, 50), 0, font_scale*1.2, (0, 255, 0))

		cnt = 0
		while cap.isOpened():
			ret, vid_frame = cap.read()
			if ret:
				cnt += 1
				vid_frame = cv2.cvtColor(vid_frame, cv2.COLOR_BGR2RGB)
				height = 500
				scale_percent = height / vid_frame.shape[0]
				width = round(vid_frame.shape[1] * scale_percent)
				vid_frame = cv2.resize(vid_frame, (width, height), interpolation=cv2.INTER_AREA)

				# draw boxes
				K = 10
				for i, (bx, by, bw, bh) in enumerate(boxes):
					if i >= K:
						break
					cv2.rectangle(vid_frame,
								  (round((bx-(bw/2))*width), round((by-(bh/2))*height)),
								  (round((bx+(bw/2))*width), round((by+(bh/2))*height)),
								  (255-25*i, 255-15*i, 255-5*i),
								  2)

					vid_frame[round((by-(bh/2))*height)-15:round((by-(bh/2))*height), round((bx-(bw/2))*width):round((bx-(bw/2))*width)+50, :] = 0
					cv2.putText(vid_frame,
								"%.4f" % pr_atts[int(vid)][i],
								(round((bx-(bw/2))*width), round((by-(bh/2))*height)-5),
								0, font_scale*.8, (255-25*i, 255-15*i, 255))

				left = 20 + int((1300 - width) / 2)
				frame[:500, left:left + width, :] = vid_frame

				frame[500:510, left:left + int(width*(cnt/total)), :] = (0, 255, 0)
				out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
			else:
				break
		cap.release()
		#
		# if vi > 2:
		# 	break

	out.release()


def main():
	# Create the parser
	arg_parser = argparse.ArgumentParser(description='Gether indepth information of datasets and predictions')

	# Add the arguments
	arg_parser.add_argument('--dataset', type=str, help='the dataset to run on', default='msrvtt')
	arg_parser.add_argument('--out_dir', type=str, help='the output directory', default=os.path.join('results', 'indepth'))
	arg_parser.add_argument('--split', type=str, help='the split', default='test')

	# Execute the parse_args() method
	args = arg_parser.parse_args()

	# Setup paths and vars
	dataset = args.dataset
	split = args.split
	args.out_dir = os.path.join(args.out_dir, dataset)
	if dataset in ['msrvtt']:
		pr_json_path = os.path.join('results', 'irv2c3dcategory_msrvtt_concat_CIDEr_32_0.0001_20_test.json')
	elif dataset in ['msvd']:
		pr_json_path = os.path.join('results', 'resnetc3d_msvd_concat_CIDEr_8_0.0001_12_test.json')
	gt_json_path = os.path.join('datasets', dataset, 'metadata', dataset+'_'+split+'_proprocessedtokens.json')

	# Load the JSON files
	gt_json = json.load(open(gt_json_path, 'r'))
	pr_json = json.load(open(pr_json_path, 'r'))

	# Specify the Scorers
	scorers = [
		(Bleu(4), ["Bleu_1", "Bleu_2", "Bleu_3", "Bleu_4"]),
		(Meteor(), "METEOR"),
		(Rouge(), "ROUGE_L"),
		(Cider(df=os.path.join('datasets', dataset, 'metadata', dataset+'_train_ciderdf.pkl')), "CIDEr"),  # todo msvd cider 0 cause of the pkl not being keyed on words
		(Spice(), "SPICE")
	]

	# Run Model Prediction Evaluations
	# pr_v_gt(gt_json, pr_json, args.out_dir, scorers)

	# Run Human Evaluations
	# gt_v_gt(gt_json, args.out_dir, scorers)

	# Make Summary Video
	gt_det_json = json.load(open(os.path.join(args.out_dir, 'gt_scores.json'), 'r'))
	pr_det_json = json.load(open(os.path.join(args.out_dir, 'pr_scores.json'), 'r'))
	if dataset == 'msrvtt':
		clip_dir = '/media/hayden/Storage2/datasets/MSRVTT/videos'
	elif dataset == 'msvd':
		clip_dir = '/media/hayden/Storage2/datasets/MSVD/videos'
	bfeat_h5_file = os.path.join('datasets', dataset, 'features', dataset + '_roi_box.h5')
	boxes_h5 = h5py.File(bfeat_h5_file, 'r')

	make_summary_video(dataset, args.out_dir, clip_dir, pr_json, gt_json, pr_det_json, gt_det_json, boxes_h5)


if __name__ == "__main__":
	main()
