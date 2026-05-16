#!/usr/bin/python

#two csv files are entered
#give each record ids
#calculate some scores based on 
#	phonetics
#calculate some hashes based on 
#	letter statistics
#calculate some enhanced matches based on
#	datatype (movienames,booknames,locationnames)
#allow adding metadata and bins through GUI
#two files with json lists are produced
list1_file=preparefilelist(file1)
list2_file=preparefilelist(file2)

with open(list1_file,'r') as f1:
	record1=f1.readline()
	scores={}
	with open(list2_file,'r') as f2:
		record2=f2.readline()
		nectarscore=nectarmatch(record1,record2)
		scores=compare_and_enhance(scores,nectarscore,scorelimit)
		if check_target_reached(scores,targettype,target): break
	save_scores(record1,scores)

#clean temp files and process saved scores
#output a csv with original data side-by-side
cleanup_and_process_saved_scores(options)
